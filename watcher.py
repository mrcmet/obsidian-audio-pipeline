"""
watcher.py — Watch a folder for new audio files and trigger the pipeline.

Uses watchdog to receive OS-level file-system events.  When a new audio
file appears, a background thread waits for it to be fully written (stable
size) before handing it off to pipeline.run_pipeline().

Public interface:
  start_watcher(config) -> None   # blocks until KeyboardInterrupt
"""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer
from watchdog.observers.polling import PollingObserver

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Supported audio file extensions (lower-cased for case-insensitive matching)
# ---------------------------------------------------------------------------
AUDIO_EXTENSIONS: frozenset[str] = frozenset({
    ".mp3",
    ".m4a",
    ".wav",
    ".ogg",
    ".flac",
    ".aac",
    ".wma",
    ".opus",
    ".webm",
})


# ---------------------------------------------------------------------------
# File stability polling
# ---------------------------------------------------------------------------

def _wait_for_stability(
    path: Path,
    interval: float = 1.0,
    checks: int = 3,
    timeout_seconds: int = 30,
) -> bool:
    """
    Block until the file at *path* has a stable, non-zero size.

    Polls the file size every *interval* seconds.  Returns True once
    *checks* consecutive polls return the same non-zero size.  Returns
    False if *timeout_seconds* elapses first, or if the file disappears.

    Args:
        path:            Path to the file to watch.
        interval:        Seconds between size checks.
        checks:          Number of consecutive equal-size polls required.
        timeout_seconds: Maximum total wait time in seconds.

    Returns:
        True if the file stabilised within the timeout, False otherwise.
    """
    max_iterations = int(timeout_seconds / interval)
    prev_size: int = -1
    stable_count: int = 0

    for _ in range(max_iterations):
        try:
            size = path.stat().st_size
        except FileNotFoundError:
            logger.warning("File disappeared while waiting for stability: %s", path.name)
            return False

        if size > 0 and size == prev_size:
            stable_count += 1
            if stable_count >= checks:
                return True
        else:
            # Size changed (or was zero) — reset the stable counter.
            stable_count = 0

        prev_size = size
        time.sleep(interval)

    logger.warning(
        "Timed out after %ds waiting for %s to stabilise",
        timeout_seconds,
        path.name,
    )
    return False


# ---------------------------------------------------------------------------
# Watchdog event handler
# ---------------------------------------------------------------------------

class AudioFileHandler(FileSystemEventHandler):
    """
    Watchdog handler that reacts to new audio files in the watch folder.

    Handles both on_created (file written directly) and on_moved (file
    copied or moved into the folder from outside).  Each qualifying file
    is dispatched to a daemon thread that waits for stability before
    calling pipeline.run_pipeline().

    Thread safety: _seen is guarded by _lock so concurrent events for the
    same path cannot trigger duplicate processing threads.
    """

    def __init__(self, config: dict) -> None:
        super().__init__()
        self.config = config
        self._seen: set[str] = set()
        self._lock = threading.Lock()

    # -- watchdog callbacks --------------------------------------------------

    def on_created(self, event) -> None:  # type: ignore[override]
        if event.is_directory:
            return
        self._handle_event(event.src_path)

    def on_moved(self, event) -> None:  # type: ignore[override]
        # Covers files moved or renamed into the watch folder (e.g. by iCloud,
        # Finder copy-paste, or a sync client completing a download).
        if event.is_directory:
            return
        self._handle_event(event.dest_path)

    def on_modified(self, event) -> None:  # type: ignore[override]
        # iCloud Drive sometimes fires modified instead of created when a file
        # finishes downloading. Treat it the same as a new file — deduplication
        # in _handle_event / pipeline._processed prevents double-processing.
        if event.is_directory:
            return
        self._handle_event(event.src_path)

    # -- internal ------------------------------------------------------------

    def _handle_event(self, path_str: str) -> None:
        """
        Validate the event path, deduplicate, and launch a processing thread.
        """
        path = Path(path_str)

        if path.suffix.lower() not in AUDIO_EXTENSIONS:
            return

        with self._lock:
            if path_str in self._seen:
                return
            self._seen.add(path_str)

        # Use a daemon thread so the process can exit cleanly on Ctrl+C
        # without waiting for an in-progress pipeline run to finish.
        thread = threading.Thread(
            target=self._process,
            args=(path,),
            daemon=True,
            name=f"pipeline-{path.name}",
        )
        thread.start()

    def _process(self, path: Path) -> None:
        """
        Wait for the file to stabilise, then run the pipeline.

        This runs in a background thread.  Errors are caught and logged here
        so a failure in one file does not affect processing of others.
        """
        logger.info("Detected audio file: %s", path.name)

        if not _wait_for_stability(path):
            logger.warning("File did not stabilise, skipping: %s", path.name)
            return

        # Deferred import keeps watcher.py importable even if pipeline.py has
        # issues, and mirrors the pattern in main.py (import after config load).
        from pipeline import run_pipeline  # noqa: PLC0415

        try:
            run_pipeline(path, self.config)
        except Exception as exc:
            # run_pipeline already logs errors internally, but we catch here
            # as an extra safety net so a threading exception is never silent.
            logger.error(
                "Unhandled error processing %s: %s",
                path.name,
                exc,
                exc_info=True,
            )


# ---------------------------------------------------------------------------
# Startup catch-up scan
# ---------------------------------------------------------------------------

def _scan_for_missed_files(watch_folder: Path, handler: AudioFileHandler) -> None:
    """
    Queue any audio files already in *watch_folder* that were not processed
    in a previous session.

    Called once at startup before the watchdog observer begins.  Handles the
    case where files arrived while the service was offline.  Files are sorted
    by mtime (oldest first) so they are processed in arrival order.
    """
    from state import is_processed  # noqa: PLC0415

    candidates: list[Path] = []
    for path in watch_folder.iterdir():
        if not path.is_file():
            continue
        if path.suffix.lower() not in AUDIO_EXTENSIONS:
            continue
        if not is_processed(path):
            candidates.append(path)

    if not candidates:
        logger.info("Startup scan: no unprocessed files found")
        return

    candidates.sort(key=lambda p: p.stat().st_mtime)
    logger.info(
        "Startup scan: found %d unprocessed file(s) — queuing for processing",
        len(candidates),
    )
    for path in candidates:
        logger.info("  Queuing missed file: %s", path.name)
        handler._handle_event(str(path))


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

def start_watcher(config: dict) -> None:
    """
    Start watching the configured folder for audio files.

    Blocks until a KeyboardInterrupt is received, then shuts the observer
    down cleanly.  The watch folder is created if it does not already exist.

    Args:
        config: Fully-loaded config dict (from config.load_config()).

    Raises:
        KeyboardInterrupt: Re-raised after the observer is stopped so the
                           caller (main.py) can log the shutdown cleanly.
        Exception:         Any unexpected observer error is propagated.
    """
    watch_folder = Path(config["watch_folder"]).expanduser().resolve()
    watch_folder.mkdir(parents=True, exist_ok=True)

    # iCloud Drive and other cloud/network folders don't reliably emit FSEvents.
    # Use PollingObserver (directory polling) for these paths so files are never missed.
    _ICLOUD_MARKERS = ("Mobile Documents", "CloudDocs", "iCloud")
    use_polling = any(marker in str(watch_folder) for marker in _ICLOUD_MARKERS)

    if use_polling:
        observer = PollingObserver(timeout=5)  # poll every 5 seconds
        logger.info("iCloud path detected — using polling observer (5 s interval)")
    else:
        observer = Observer()

    logger.info("Watching for audio files in: %s", watch_folder)
    logger.info(
        "Supported extensions: %s",
        ", ".join(sorted(AUDIO_EXTENSIONS)),
    )

    handler = AudioFileHandler(config)
    observer.schedule(handler, str(watch_folder), recursive=False)
    observer.start()

    logger.info("Watcher started — waiting for files (Ctrl+C to stop)")
    _scan_for_missed_files(watch_folder, handler)

    try:
        while True:
            time.sleep(1)
            # Check if the observer thread died unexpectedly.
            if not observer.is_alive():
                logger.error("Watchdog observer thread died unexpectedly — restarting")
                observer.start()
    except KeyboardInterrupt:
        logger.info("Shutdown signal received — stopping watcher")
        observer.stop()
    finally:
        observer.join()
        logger.info("Watcher stopped")

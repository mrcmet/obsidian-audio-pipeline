"""
main.py — Entry point. Loads config, sets up logging, starts watcher.

Run with:
    python main.py
"""

import argparse
import logging
import sys
from pathlib import Path


def _configure_logging() -> None:
    """
    Set up the root logger to emit to both stdout and pipeline.log.
    All pipeline modules use child loggers (logging.getLogger(__name__))
    so they inherit this configuration automatically.
    """
    # Reconfigure stdout/stderr to UTF-8 for direct runs ("python main.py").
    # When launched by tray.py, PYTHONUTF8=1 is set in the subprocess env
    # instead — both paths avoid UnicodeEncodeError on Windows cp1252 consoles.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    log_format = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    date_format = "%Y-%m-%d %H:%M:%S"

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    # Suppress one-time cosmetic noise from third-party libraries.
    logging.getLogger("lightning.pytorch.utilities.migration.utils").setLevel(logging.ERROR)

    # Stdout handler — useful for interactive / foreground development
    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setLevel(logging.INFO)
    stdout_handler.setFormatter(logging.Formatter(log_format, datefmt=date_format))

    # File handler — persists across restarts for debugging
    log_file = Path(__file__).parent / "pipeline.log"
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(logging.Formatter(log_format, datefmt=date_format))

    root_logger.addHandler(stdout_handler)
    root_logger.addHandler(file_handler)


def main() -> None:
    parser = argparse.ArgumentParser(description="Obsidian Audio Pipeline")
    parser.add_argument(
        "--retry-failed",
        action="store_true",
        help="Clear failed-file records so they are re-queued on startup scan.",
    )
    args = parser.parse_args()

    _configure_logging()

    logger = logging.getLogger(__name__)
    logger.info("Obsidian Audio Pipeline starting up")

    if args.retry_failed:
        from state import clear_failed  # noqa: PLC0415
        clear_failed()
        logger.info("--retry-failed: cleared failed-file records — they will be re-queued")

    # Config must load before anything else — all modules receive it as a
    # parameter rather than importing it globally (convention from CLAUDE.md).
    try:
        from config import load_config
        config = load_config()
    except Exception as exc:
        # Use print here as a fallback — logging may not be fully wired yet
        # if the import itself fails, though _configure_logging() runs first.
        logging.getLogger(__name__).error(
            "Failed to load configuration: %s", exc, exc_info=True
        )
        sys.exit(1)

    logger.info(
        "Config loaded — watching '%s', vault inbox '%s'",
        config["watch_folder"],
        config["obsidian_vault_folder"],
    )

    # Import watcher only after config is confirmed good so that import errors
    # in watcher.py (e.g. missing watchdog) surface with a clear log message.
    try:
        from watcher import start_watcher
    except ImportError as exc:
        logger.error(
            "Could not import watcher module: %s. "
            "Ensure all dependencies are installed: pip install -r requirements.txt",
            exc,
            exc_info=True,
        )
        sys.exit(1)

    try:
        start_watcher(config)
    except KeyboardInterrupt:
        logger.info("Shutting down — KeyboardInterrupt received")
        sys.exit(0)
    except Exception as exc:
        logger.error("Watcher crashed unexpectedly: %s", exc, exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()

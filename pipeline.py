"""
pipeline.py — Orchestrate the full audio-to-note pipeline.

Calls each stage in sequence and handles audio file disposition after a
successful run.  Tracks processed files in-process to prevent
double-processing if the watcher fires more than once for the same path.

Public interface:
  run_pipeline(audio_path, config) -> Path | None
"""

from __future__ import annotations

import logging
import shutil
from datetime import datetime
from pathlib import Path

from transcriber import transcribe
from llm import extract_note_data
from note_writer import render_and_write

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# In-process deduplication — prevents a file from being processed twice if
# the watcher emits duplicate events (e.g. on_created + on_modified).
# Uses resolved absolute paths as keys for reliable comparison.
# ---------------------------------------------------------------------------
_processed: set[Path] = set()


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

def run_pipeline(audio_path: Path, config: dict) -> Path | None:
    """
    Process one audio file through the full pipeline.

    Stages:
      1. Transcribe audio → plain text + duration
      2. LLM extraction → structured note_data dict
      3. Write note → .md file in Obsidian vault
      4. Handle source audio (archive / delete / leave)

    Args:
        audio_path: Path to the audio file to process.
        config:     Fully-loaded config dict (from config.load_config()).

    Returns:
        Path to the written .md note on success, or None if the file was
        skipped (already processed) or the pipeline encountered an error.
    """
    audio_path = audio_path.resolve()

    if audio_path in _processed:
        logger.info("Already processed, skipping: %s", audio_path.name)
        return None

    logger.info("Processing: %s", audio_path.name)
    _processed.add(audio_path)

    try:
        # Stage 1: Transcribe ------------------------------------------------
        logger.info("Stage 1/4 — Transcribing %s", audio_path.name)
        transcript, duration = transcribe(audio_path, config["transcriber"])
        logger.info(
            "Transcription complete. Duration: %s, Length: %d chars",
            f"{duration:.1f}s" if duration is not None else "unknown",
            len(transcript),
        )

        # Stage 2: LLM extraction --------------------------------------------
        logger.info("Stage 2/4 — Extracting note data via LLM")
        note_data = extract_note_data(transcript, duration, audio_path, config)

        # Attach transcript and duration so note_writer can render them.
        # These are not part of the LLM JSON response — they come from earlier
        # stages and are injected here to keep stage contracts clean.
        note_data["transcript"] = transcript
        note_data["duration_seconds"] = duration

        # Stage 3: Write note ------------------------------------------------
        logger.info("Stage 3/4 — Writing note to vault")
        note_path = render_and_write(note_data, audio_path, config)
        logger.info("Note written: %s", note_path)

        # Stage 4: Handle audio file -----------------------------------------
        logger.info("Stage 4/4 — Handling source audio file")
        _handle_audio_file(audio_path, config)

        return note_path

    except Exception as exc:
        logger.error(
            "Pipeline failed for %s: %s",
            audio_path.name,
            exc,
            exc_info=True,
        )
        # Remove from the processed set so a manual retry is possible without
        # restarting the service.
        _processed.discard(audio_path)
        return None


# ---------------------------------------------------------------------------
# Audio file disposition
# ---------------------------------------------------------------------------

def _handle_audio_file(audio_path: Path, config: dict) -> None:
    """
    Archive, delete, or leave the source audio file as configured.

    Args:
        audio_path: Resolved absolute path to the source audio file.
        config:     Fully-loaded config dict.

    Raises:
        OSError: If an archive or delete operation fails at the OS level.
    """
    action: str = config["on_complete"]["audio_file_action"]

    if action == "archive":
        archive_dir = Path(config["archive_folder"])
        archive_dir.mkdir(parents=True, exist_ok=True)

        dest = archive_dir / audio_path.name
        if dest.exists():
            # Avoid silently overwriting a previously archived file with the
            # same name — append a timestamp to make the destination unique.
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            dest = archive_dir / f"{audio_path.stem}_{ts}{audio_path.suffix}"

        shutil.move(str(audio_path), str(dest))
        logger.info("Archived to: %s", dest)

    elif action == "delete":
        audio_path.unlink()
        logger.info("Deleted: %s", audio_path.name)

    elif action == "leave":
        logger.info("Left in place: %s", audio_path.name)

    else:
        # Config validation in config.py should prevent reaching here, but
        # defensive logging beats a silent no-op if something slips through.
        logger.warning(
            "Unknown audio_file_action: %r — leaving file in place",
            action,
        )

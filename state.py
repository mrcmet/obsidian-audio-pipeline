"""
state.py — Persistent record of successfully processed audio files.

Survives process restarts so the watcher can detect files that arrived
while the service was offline and process them on the next startup.

State is keyed by (resolved_path, mtime) so a file replaced with new
content (same name, different mtime) is correctly treated as unprocessed.

Public interface:
  is_processed(path)   -> bool
  mark_processed(path) -> None
"""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path

logger = logging.getLogger(__name__)

_STATE_FILE = Path(__file__).parent / "pipeline_state.json"
_lock = threading.Lock()


def is_processed(path: Path) -> bool:
    """Return True if this exact file (resolved path + mtime) was already processed."""
    try:
        key = _make_key(path)
    except OSError:
        return False
    return key in _load_keys()


def mark_processed(path: Path) -> None:
    """
    Record *path* as successfully processed.

    Called before audio file disposition so the file still exists for stat().
    Thread-safe — safe to call from concurrent pipeline threads.
    """
    try:
        key = _make_key(path)
    except OSError as exc:
        logger.warning("Could not stat %s for state tracking: %s", path.name, exc)
        return

    with _lock:
        data = _load_raw()
        entry = {"path": key[0], "mtime": key[1]}
        if entry not in data["processed"]:
            data["processed"].append(entry)
            _save_raw(data)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _make_key(path: Path) -> tuple[str, float]:
    resolved = path.resolve()
    return (str(resolved), resolved.stat().st_mtime)


def _load_raw() -> dict:
    if not _STATE_FILE.exists():
        return {"processed": []}
    try:
        return json.loads(_STATE_FILE.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("Could not read state file (%s) — starting fresh", exc)
        return {"processed": []}


def _load_keys() -> set[tuple[str, float]]:
    data = _load_raw()
    return {(item["path"], item["mtime"]) for item in data.get("processed", [])}


def _save_raw(data: dict) -> None:
    try:
        _STATE_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except OSError as exc:
        logger.error("Could not write state file %s: %s", _STATE_FILE, exc)

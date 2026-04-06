"""
vault_tags.py — Scan the Obsidian vault for all unique tags.

Reads both YAML frontmatter tags and inline #hashtags from every .md file
under the configured vault folder. Results are cached in-process so the
disk scan only happens once per session.

Public interface:
  get_vault_tags(vault_path)  -> list[str]   # cached
  refresh_tags(vault_path)    -> list[str]   # forces re-scan
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

import frontmatter

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level cache — keyed by resolved absolute path string so that "~/"
# and an absolute equivalent of the same folder resolve to the same entry.
# ---------------------------------------------------------------------------
_tag_cache: dict[str, list[str]] = {}

# Matches inline #hashtags.  Requires the tag to start with a letter so
# plain # headings and numeric anchors are not captured.  Allows letters,
# digits, underscores, hyphens, and forward slashes (nested Obsidian tags).
_INLINE_TAG_RE = re.compile(r"#([A-Za-z][A-Za-z0-9_/-]*)")


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

def get_vault_tags(vault_path: str | Path) -> list[str]:
    """
    Return a sorted list of unique tags found in the vault.

    Results are cached after the first call for a given path.  Subsequent
    calls with the same path return the cached list instantly without any
    further disk I/O.

    Args:
        vault_path: Path to the Obsidian vault (or inbox subfolder).
                    ~ is expanded automatically.

    Returns:
        Sorted list of lowercase tag strings, without the leading # prefix.

    Raises:
        OSError: If vault_path does not exist or cannot be read.
    """
    key = _resolve_key(vault_path)
    if key in _tag_cache:
        logger.debug("Returning cached tags for %s (%d tags)", key, len(_tag_cache[key]))
        return _tag_cache[key]

    tags = _scan_vault(Path(key))
    _tag_cache[key] = tags
    return tags


def refresh_tags(vault_path: str | Path) -> list[str]:
    """
    Force a re-scan of the vault, bypassing the cache.

    Useful for long-running sessions where the vault has changed since the
    last scan.

    Args:
        vault_path: Path to the Obsidian vault.  ~ is expanded automatically.

    Returns:
        Sorted list of lowercase tag strings after the fresh scan.

    Raises:
        OSError: If vault_path does not exist or cannot be read.
    """
    key = _resolve_key(vault_path)
    logger.info("Forcing vault tag re-scan for %s", key)
    tags = _scan_vault(Path(key))
    _tag_cache[key] = tags
    return tags


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _resolve_key(vault_path: str | Path) -> str:
    """Expand ~ and return an absolute path string suitable as a cache key."""
    return str(Path(vault_path).expanduser().resolve())


def _scan_vault(vault_path: Path) -> list[str]:
    """
    Walk *vault_path* recursively, collect every tag, and return a sorted
    deduplicated list.

    Skips any path whose components include '.obsidian' (Obsidian system
    folder).  Per-file parse failures are logged as warnings and skipped so
    that a single corrupt file does not abort the whole scan.

    Args:
        vault_path: Resolved absolute Path to the vault root.

    Returns:
        Sorted list of lowercase tag strings.

    Raises:
        OSError: If vault_path does not exist.
    """
    if not vault_path.exists():
        raise OSError(
            f"Vault path does not exist: {vault_path}. "
            "Update obsidian_vault_folder in config.yaml."
        )

    tags: set[str] = set()
    files_scanned = 0
    files_failed = 0

    for md_file in vault_path.rglob("*.md"):
        # Skip anything inside Obsidian's own system folder.
        if ".obsidian" in md_file.parts:
            continue

        try:
            _extract_tags_from_file(md_file, tags)
            files_scanned += 1
        except Exception as exc:
            logger.warning(
                "Could not parse tags from %s: %s — skipping",
                md_file,
                exc,
            )
            files_failed += 1

    logger.info(
        "Vault tag scan complete: %d tags from %d files (%d skipped) in %s",
        len(tags),
        files_scanned,
        files_failed,
        vault_path,
    )

    return sorted(tags)


def _extract_tags_from_file(md_file: Path, tags: set[str]) -> None:
    """
    Parse a single .md file and add any discovered tags into *tags*.

    Two sources are checked:
      1. YAML frontmatter — the 'tags' or 'tag' key (list or single string).
      2. Inline #hashtags in the document body.

    Args:
        md_file: Path to the markdown file to parse.
        tags:    Mutable set to add discovered tags into (modified in-place).
    """
    raw_text = md_file.read_text(encoding="utf-8", errors="replace")

    # --- Frontmatter tags ---------------------------------------------------
    try:
        post = frontmatter.loads(raw_text)
        for fm_key in ("tags", "tag"):
            value = post.metadata.get(fm_key)
            if value is None:
                continue
            # Normalise to a list — frontmatter may give us a str, list, or
            # something YAML-coerced (e.g. an int if someone wrote `tags: 1`).
            if isinstance(value, list):
                raw_tags = value
            else:
                raw_tags = [value]

            for raw_tag in raw_tags:
                normalised = _normalise_tag(raw_tag)
                if normalised:
                    tags.add(normalised)
    except Exception as exc:
        # frontmatter parse failure — fall through to inline scan, but log.
        logger.debug("Frontmatter parse failed for %s: %s", md_file.name, exc)

    # --- Inline hashtags ----------------------------------------------------
    for match in _INLINE_TAG_RE.finditer(raw_text):
        normalised = _normalise_tag(match.group(1))
        if normalised:
            tags.add(normalised)


def _normalise_tag(raw: object) -> str:
    """
    Convert a raw tag value to a clean lowercase string without leading '#'.

    Returns an empty string if the value cannot be normalised (e.g. None, int
    that looks like a date component).
    """
    if raw is None:
        return ""
    text = str(raw).strip().lstrip("#").lower()
    # Discard empty strings and purely numeric values (e.g. YAML date parts).
    if not text or text.isdigit():
        return ""
    return text

"""
note_writer.py — Render structured note data as Obsidian markdown.

Consumes the note_data dict produced by llm.extract_note_data(), merges it
with Jinja2 template variables derived from the audio file path and config,
and writes the resulting .md file to the configured vault folder.

Public interface:
    render_and_write(note_data, audio_path, config) -> Path

Config keys consumed (config["note"]):
    template_file              : str | None — path to a custom .j2 template
    include_full_transcript    : bool
    collapse_transcript        : bool
    subfolder_pattern          : str        — e.g. "{year}/{month}"

Config keys consumed (top-level):
    obsidian_vault_folder      : str

Errors in all stages are logged and re-raised as RuntimeError so the
pipeline orchestrator can handle cleanup consistently.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

import jinja2

logger = logging.getLogger(__name__)

# Maximum characters allowed in the filename stem (title portion) to stay
# comfortably within the 255-byte limit on most filesystems.
_MAX_TITLE_CHARS = 100

# ---------------------------------------------------------------------------
# Default Jinja2 template
# ---------------------------------------------------------------------------

DEFAULT_TEMPLATE = """\
---
title: "{{ title }}"
date: {{ date }}
time: {{ time }}
audio_file: {{ audio_filename }}
duration: {{ duration }}
tags: [{{ tags | join(', ') }}]
---

# {{ title }}

> {{ datetime_human }} · {{ audio_filename }}{% if duration %} · {{ duration }}{% endif %}

{% if attendees %}
**Attendees:** {% for name in attendees %}[[{{ name }}]]{% if not loop.last %}, {% endif %}{% endfor %}

{% endif %}
## Summary

{{ summary }}

{% if key_points %}
## Key Points

{% for point in key_points %}
- {{ point }}
{% endfor %}
{% endif %}
{% if todos %}
## Action Items

{% for todo in todos %}
- [ ] {{ todo.task }}{% if todo.owner %} — *{{ todo.owner }}*{% endif %}{% if todo.due %} *(due: {{ todo.due }})*{% endif %}

{% endfor %}
{% endif %}
{% if decisions %}
## Decisions

{% for decision in decisions %}
- {{ decision }}
{% endfor %}
{% endif %}
{% if follow_ups %}
## Follow-ups

{% for item in follow_ups %}
- {{ item }}
{% endfor %}
{% endif %}
{% for section_name, content in custom_sections.items() %}
## {{ section_name }}

{{ content }}

{% endfor %}
{% if include_transcript and transcript %}
## Transcript

{% if collapse_transcript %}
<details>
<summary>Full transcript</summary>

{{ transcript }}

</details>
{% else %}
{{ transcript }}
{% endif %}
{% endif %}
"""


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _sanitize_filename(title: str) -> str:
    """
    Convert an arbitrary title string into a safe filename stem.

    Replaces characters that are illegal or problematic on Windows, macOS,
    and Linux filesystems with a hyphen. Collapses runs of hyphens and
    whitespace, strips leading/trailing whitespace and hyphens, and truncates
    to _MAX_TITLE_CHARS characters.

    Args:
        title: The raw title string from the LLM.

    Returns:
        A sanitized string suitable for use as a filename stem.
    """
    if not title:
        return "untitled"

    # Replace filesystem-illegal and Obsidian-problematic characters.
    # Covers: / \ : * ? " < > | and the null byte.
    sanitized = re.sub(r'[/\\:*?"<>|\x00]', "-", title)

    # Collapse consecutive whitespace into a single space.
    sanitized = re.sub(r"\s+", " ", sanitized)

    # Collapse consecutive hyphens (e.g. from multiple replaced chars).
    sanitized = re.sub(r"-{2,}", "-", sanitized)

    # Strip leading/trailing whitespace and hyphens.
    sanitized = sanitized.strip(" -")

    # Enforce maximum length.
    sanitized = sanitized[:_MAX_TITLE_CHARS].rstrip(" -")

    return sanitized or "untitled"


def _format_duration(duration_seconds: float | None) -> str:
    """
    Format a duration in seconds as a human-readable string like "12m 34s".

    Args:
        duration_seconds: Total duration in seconds, or None if unavailable.

    Returns:
        Formatted duration string, or empty string if duration_seconds is None.
    """
    if duration_seconds is None:
        return ""

    total_seconds = int(duration_seconds)
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)

    if hours > 0:
        return f"{hours}h {minutes}m {seconds}s"
    if minutes > 0:
        return f"{minutes}m {seconds}s"
    return f"{seconds}s"


def _format_datetime_human(recorded_at) -> str:
    """
    Format a datetime as a human-readable string in a cross-platform way.

    strftime's '%-I' (no-pad hour) is Linux/macOS only. This function uses
    '%I' and strips the leading zero manually for portability.

    Args:
        recorded_at: A datetime object.

    Returns:
        A string like "Monday, April 05, 2026 at 2:30 PM".
    """
    # Build each component separately to avoid platform-specific format codes.
    day_name = recorded_at.strftime("%A")
    month_day_year = recorded_at.strftime("%B %d, %Y")
    hour_12 = recorded_at.strftime("%I").lstrip("0") or "12"  # never empty
    minute = recorded_at.strftime("%M")
    am_pm = recorded_at.strftime("%p")
    return f"{day_name}, {month_day_year} at {hour_12}:{minute} {am_pm}"


def _build_context(
    note_data: dict,
    audio_path: Path,
    config: dict,
) -> dict:
    """
    Build the Jinja2 template context dict from note_data, audio_path, and config.

    All fields use .get() with safe defaults so that a partially populated
    note_data dict (e.g. during testing) does not raise KeyError.

    Args:
        note_data:  The structured dict returned by llm.extract_note_data().
        audio_path: Path to the original audio file (provides the filename).
        config:     The full config dict from load_config().

    Returns:
        A flat dict ready to pass as **kwargs to template.render().
    """
    recorded_at = note_data.get("recorded_at")
    if recorded_at is None:
        from datetime import datetime as _datetime
        logger.warning(
            "note_data missing 'recorded_at'; defaulting to current time"
        )
        recorded_at = _datetime.now()

    note_cfg = config.get("note", {})

    return {
        "title":             note_data.get("title", "Untitled"),
        "date":              recorded_at.strftime("%Y-%m-%d"),
        "time":              recorded_at.strftime("%H:%M"),
        "datetime_human":    _format_datetime_human(recorded_at),
        "audio_filename":    audio_path.name,
        "duration":          _format_duration(note_data.get("duration_seconds")),
        "tags":              note_data.get("tags", []),
        "attendees":         note_data.get("attendees", []),
        "summary":           note_data.get("summary", ""),
        "key_points":        note_data.get("key_points", []),
        "todos":             note_data.get("todos", []),
        "decisions":         note_data.get("decisions", []),
        "follow_ups":        note_data.get("follow_ups", []),
        "custom_sections":   note_data.get("custom_sections", {}),
        "transcript":        note_data.get("transcript", ""),
        "include_transcript": note_cfg.get("include_full_transcript", True),
        "collapse_transcript": note_cfg.get("collapse_transcript", True),
    }


def _load_template(config: dict) -> jinja2.Template:
    """
    Load and return the Jinja2 Template to use for rendering.

    If config["note"]["template_file"] is set, loads the template from that
    file path. Otherwise falls back to the built-in DEFAULT_TEMPLATE string.

    Jinja2 environment settings:
      - trim_blocks=True      — removes the newline after a block tag
      - lstrip_blocks=True    — strips leading whitespace before block tags
      - keep_trailing_newline — preserves the trailing newline in the source
      - undefined=Undefined   — raises on missing variables (explicit failure)

    Args:
        config: The full config dict from load_config().

    Returns:
        A compiled jinja2.Template ready for rendering.

    Raises:
        FileNotFoundError: If template_file is set but does not exist.
        jinja2.TemplateSyntaxError: If the template file contains a syntax error.
    """
    template_file = config.get("note", {}).get("template_file")

    env_kwargs = {
        "trim_blocks": True,
        "lstrip_blocks": True,
        "keep_trailing_newline": True,
        "undefined": jinja2.Undefined,
    }

    if template_file:
        path = Path(template_file)
        if not path.exists():
            raise FileNotFoundError(
                f"Template file not found: {path}. "
                "Check note.template_file in config.yaml."
            )
        logger.debug("Loading custom template from %s", path)
        env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(str(path.parent)),
            **env_kwargs,
        )
        return env.get_template(path.name)

    logger.debug("Using built-in default template")
    env = jinja2.Environment(**env_kwargs)
    return env.from_string(DEFAULT_TEMPLATE)


def _resolve_output_path(note_data: dict, config: dict) -> Path:
    """
    Determine the full filesystem path for the output .md file.

    Path structure:
        <obsidian_vault_folder> / <subfolder> / <date> <safe_title>.md

    The subfolder is derived from subfolder_pattern by substituting
    {year}, {month}, {day} placeholders with values from recorded_at.
    An empty pattern places the note directly in obsidian_vault_folder.

    Args:
        note_data: The structured dict returned by llm.extract_note_data().
        config:    The full config dict from load_config().

    Returns:
        A Path object for the output file (parent directories may not yet exist).
    """
    vault_folder = Path(config["obsidian_vault_folder"])
    subfolder_pattern: str = config.get("note", {}).get("subfolder_pattern", "")
    recorded_at = note_data.get("recorded_at")

    if recorded_at is None:
        from datetime import datetime as _datetime
        recorded_at = _datetime.now()

    if subfolder_pattern:
        subfolder = subfolder_pattern.format(
            year=recorded_at.strftime("%Y"),
            month=recorded_at.strftime("%m"),
            day=recorded_at.strftime("%d"),
        )
        output_dir = vault_folder / subfolder
    else:
        output_dir = vault_folder

    safe_title = _sanitize_filename(note_data.get("title", "untitled"))
    date_str = recorded_at.strftime("%Y-%m-%d")
    filename = f"{date_str} {safe_title}.md"

    return output_dir / filename


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------


def render_and_write(note_data: dict, audio_path: Path, config: dict) -> Path:
    """
    Render note_data using a Jinja2 template and write the result to the vault.

    Steps:
      1. Load the Jinja2 template (custom file or built-in default).
      2. Build the template context from note_data, audio_path, and config.
      3. Render the template.
      4. Resolve the output path, creating parent directories as needed.
      5. Write the rendered markdown to disk (UTF-8, overwriting if present).

    Args:
        note_data:  Structured dict returned by llm.extract_note_data().
                    Expected keys: title, summary, key_points, todos, decisions,
                    attendees, follow_ups, tags, custom_sections, recorded_at,
                    raw_llm_response. Optional keys: duration_seconds, transcript.
        audio_path: Path to the original audio file.
        config:     Full config dict from load_config().

    Returns:
        The Path to the written .md file.

    Raises:
        RuntimeError: If template loading, rendering, or file writing fails.
                      The underlying exception is chained for full traceback.
    """
    try:
        template = _load_template(config)
    except Exception as exc:
        logger.error("Failed to load template: %s", exc)
        raise RuntimeError(f"Note writing failed (template load): {exc}") from exc

    try:
        context = _build_context(note_data, audio_path, config)
    except Exception as exc:
        logger.error("Failed to build template context: %s", exc)
        raise RuntimeError(
            f"Note writing failed (context build): {exc}"
        ) from exc

    try:
        rendered = template.render(**context)
    except jinja2.TemplateError as exc:
        logger.error(
            "Jinja2 template rendering failed for %s: %s",
            audio_path.name,
            exc,
        )
        raise RuntimeError(
            f"Note writing failed (template render): {exc}"
        ) from exc

    output_path = _resolve_output_path(note_data, config)
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered, encoding="utf-8")
    except OSError as exc:
        logger.error("Failed to write note file %s: %s", output_path, exc)
        raise RuntimeError(f"Note writing failed (file write): {exc}") from exc

    logger.info("Note written: %s", output_path)
    return output_path

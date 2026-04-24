"""
tests/test_note_writer.py — Unit tests for note_writer.py.

Tests cover filename sanitization, duration formatting, template context
construction, template loading, output path resolution, and full render+write.

All filesystem interaction uses pytest's tmp_path fixture — no mocking.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from note_writer import (
    DEFAULT_TEMPLATE,
    _build_context,
    _format_duration,
    _load_template,
    _resolve_output_path,
    _sanitize_filename,
    render_and_write,
)


# ---------------------------------------------------------------------------
# _sanitize_filename
# ---------------------------------------------------------------------------


class TestSanitizeFilename:
    def test_normal_title_passes_through(self):
        assert _sanitize_filename("Team Standup Notes") == "Team Standup Notes"

    @pytest.mark.parametrize("char", list('/\\:*?"<>|'))
    def test_illegal_chars_replaced_with_hyphen(self, char: str):
        result = _sanitize_filename(f"before{char}after")
        assert char not in result
        assert "before" in result
        assert "after" in result

    def test_consecutive_hyphens_collapsed(self):
        # Two illegal chars side-by-side produce "before--after" which must collapse.
        result = _sanitize_filename("before/*after")
        assert "--" not in result

    def test_leading_and_trailing_hyphens_stripped(self):
        result = _sanitize_filename("/leading and trailing/")
        assert not result.startswith("-")
        assert not result.endswith("-")

    def test_empty_string_returns_untitled(self):
        assert _sanitize_filename("") == "untitled"

    def test_only_illegal_chars_returns_untitled(self):
        assert _sanitize_filename('/?*:"') == "untitled"

    def test_long_title_truncated_to_100_chars(self):
        long = "a" * 150
        result = _sanitize_filename(long)
        assert len(result) <= 100

    def test_exactly_100_chars_not_truncated(self):
        title = "a" * 100
        result = _sanitize_filename(title)
        assert result == title

    def test_null_byte_replaced(self):
        result = _sanitize_filename("hello\x00world")
        assert "\x00" not in result


# ---------------------------------------------------------------------------
# _format_duration
# ---------------------------------------------------------------------------


class TestFormatDuration:
    def test_none_returns_empty_string(self):
        assert _format_duration(None) == ""

    def test_seconds_only(self):
        assert _format_duration(45) == "45s"

    def test_zero_seconds(self):
        assert _format_duration(0) == "0s"

    def test_exactly_one_minute(self):
        assert _format_duration(60) == "1m 0s"

    def test_minutes_and_seconds(self):
        assert _format_duration(75) == "1m 15s"

    def test_exactly_one_hour(self):
        assert _format_duration(3600) == "1h 0m 0s"

    def test_hours_minutes_seconds(self):
        assert _format_duration(3723) == "1h 2m 3s"

    def test_float_truncated_to_int(self):
        # 90.9 seconds → 1m 30s (int truncation, not rounding)
        assert _format_duration(90.9) == "1m 30s"


# ---------------------------------------------------------------------------
# _build_context
# ---------------------------------------------------------------------------


def _make_config(
    *,
    include_full_transcript: bool = True,
    collapse_transcript: bool = True,
    vault_folder: str = "/vault",
) -> dict:
    return {
        "obsidian_vault_folder": vault_folder,
        "note": {
            "include_full_transcript": include_full_transcript,
            "collapse_transcript": collapse_transcript,
            "subfolder_pattern": "",
            "template_file": None,
        },
    }


def _make_note_data(recorded_at: datetime | None = None, **overrides) -> dict:
    base = {
        "title": "Test Note",
        "summary": "A test summary.",
        "key_points": ["Point A", "Point B"],
        "todos": [{"task": "Do something", "owner": "Alice", "due": None}],
        "decisions": ["Use Python"],
        "attendees": ["Alice Smith", "Bob Jones"],
        "follow_ups": ["Check later"],
        "tags": ["meeting", "test"],
        "custom_sections": {},
        "transcript": "This is the transcript.",
        "duration_seconds": 90.0,
        "recorded_at": recorded_at or datetime(2026, 4, 20, 14, 30, 0),
    }
    base.update(overrides)
    return base


class TestBuildContext:
    def test_all_expected_keys_present(self, tmp_path: Path):
        note_data = _make_note_data()
        config = _make_config()
        ctx = _build_context(note_data, tmp_path / "test.m4a", config)

        expected_keys = {
            "title", "date", "time", "datetime_human", "audio_filename",
            "duration", "tags", "attendees", "summary", "key_points",
            "todos", "decisions", "follow_ups", "custom_sections",
            "transcript", "include_transcript", "collapse_transcript",
        }
        assert expected_keys.issubset(ctx.keys())

    def test_include_transcript_comes_from_config(self, tmp_path: Path):
        note_data = _make_note_data()
        config = _make_config(include_full_transcript=False)
        ctx = _build_context(note_data, tmp_path / "test.m4a", config)
        assert ctx["include_transcript"] is False

    def test_collapse_transcript_comes_from_config(self, tmp_path: Path):
        note_data = _make_note_data()
        config = _make_config(collapse_transcript=False)
        ctx = _build_context(note_data, tmp_path / "test.m4a", config)
        assert ctx["collapse_transcript"] is False

    def test_missing_recorded_at_defaults_to_current_time(self, tmp_path: Path):
        note_data = _make_note_data()
        note_data["recorded_at"] = None
        config = _make_config()
        # Must not raise; date/time fields must be populated strings.
        ctx = _build_context(note_data, tmp_path / "test.m4a", config)
        assert ctx["date"]  # non-empty
        assert ctx["time"]  # non-empty

    def test_duration_is_formatted_string_not_raw_seconds(self, tmp_path: Path):
        note_data = _make_note_data(duration_seconds=75.0)
        config = _make_config()
        ctx = _build_context(note_data, tmp_path / "test.m4a", config)
        assert ctx["duration"] == "1m 15s"

    def test_audio_filename_is_basename_only(self, tmp_path: Path):
        note_data = _make_note_data()
        audio_path = tmp_path / "subdir" / "my_recording.m4a"
        config = _make_config()
        ctx = _build_context(note_data, audio_path, config)
        assert ctx["audio_filename"] == "my_recording.m4a"

    def test_date_and_time_derived_from_recorded_at(self, tmp_path: Path):
        note_data = _make_note_data(recorded_at=datetime(2026, 4, 20, 9, 5, 0))
        config = _make_config()
        ctx = _build_context(note_data, tmp_path / "test.m4a", config)
        assert ctx["date"] == "2026-04-20"
        assert ctx["time"] == "09:05"


# ---------------------------------------------------------------------------
# _load_template
# ---------------------------------------------------------------------------


class TestLoadTemplate:
    def test_null_template_file_loads_default(self):
        config = _make_config()
        template = _load_template(config)
        # Should render without error with a minimal context.
        rendered = template.render(
            title="T", date="2026-04-20", time="09:00",
            datetime_human="Monday, April 20, 2026 at 9:00 AM",
            audio_filename="f.m4a", duration="1m 0s",
            tags=[], attendees=[], summary="S", key_points=[],
            todos=[], decisions=[], follow_ups=[], custom_sections={},
            transcript="", include_transcript=False, collapse_transcript=False,
        )
        assert "T" in rendered

    def test_valid_template_file_path_loaded(self, tmp_path: Path):
        tpl_file = tmp_path / "custom.j2"
        tpl_file.write_text("Hello {{ title }}", encoding="utf-8")
        config = _make_config()
        config["note"]["template_file"] = str(tpl_file)
        template = _load_template(config)
        rendered = template.render(title="World")
        assert rendered == "Hello World"

    def test_nonexistent_template_file_raises_file_not_found(self):
        config = _make_config()
        config["note"]["template_file"] = "/nonexistent/path/template.j2"
        with pytest.raises(FileNotFoundError, match="Template file not found"):
            _load_template(config)


# ---------------------------------------------------------------------------
# _resolve_output_path
# ---------------------------------------------------------------------------


class TestResolveOutputPath:
    def test_no_subfolder_pattern_note_goes_in_vault_folder(self, tmp_path: Path):
        note_data = _make_note_data(recorded_at=datetime(2026, 4, 20, 14, 0, 0))
        config = _make_config(vault_folder=str(tmp_path))
        output = _resolve_output_path(note_data, config)
        assert output.parent == tmp_path

    def test_year_month_pattern_creates_correct_subdirectory(self, tmp_path: Path):
        note_data = _make_note_data(recorded_at=datetime(2026, 4, 20, 14, 0, 0))
        config = _make_config(vault_folder=str(tmp_path))
        config["note"]["subfolder_pattern"] = "{year}/{month}"
        output = _resolve_output_path(note_data, config)
        assert output.parent == tmp_path / "2026" / "04"

    def test_filename_contains_date_and_sanitized_title(self, tmp_path: Path):
        note_data = _make_note_data(
            title="Q3 Budget: Review",
            recorded_at=datetime(2026, 4, 20, 14, 0, 0),
        )
        config = _make_config(vault_folder=str(tmp_path))
        output = _resolve_output_path(note_data, config)
        assert output.name.startswith("2026-04-20")
        assert ":" not in output.name
        assert output.suffix == ".md"

    def test_title_sanitization_applied_in_filename(self, tmp_path: Path):
        note_data = _make_note_data(title='Bad/Title:Here*Now"End')
        config = _make_config(vault_folder=str(tmp_path))
        output = _resolve_output_path(note_data, config)
        for illegal_char in '/\\:*?"<>|':
            assert illegal_char not in output.name


# ---------------------------------------------------------------------------
# render_and_write
# ---------------------------------------------------------------------------


def _make_full_config(vault_folder: str, template_file: str | None = None) -> dict:
    return {
        "obsidian_vault_folder": vault_folder,
        "note": {
            "template_file": template_file,
            "include_full_transcript": True,
            "collapse_transcript": True,
            "subfolder_pattern": "",
            "fallback_tags": ["meeting"],
        },
    }


class TestRenderAndWrite:
    def test_happy_path_file_written_with_title_in_content(self, tmp_path: Path):
        note_data = _make_note_data(recorded_at=datetime(2026, 4, 20, 14, 30, 0))
        config = _make_full_config(vault_folder=str(tmp_path))
        audio_path = tmp_path / "recording.m4a"
        audio_path.touch()

        output = render_and_write(note_data, audio_path, config)

        assert output.exists()
        content = output.read_text(encoding="utf-8")
        assert "Test Note" in content

    def test_custom_template_file_used_when_configured(self, tmp_path: Path):
        tpl_file = tmp_path / "my.j2"
        tpl_file.write_text("CUSTOM:{{ title }}", encoding="utf-8")
        note_data = _make_note_data(recorded_at=datetime(2026, 4, 20, 14, 30, 0))
        config = _make_full_config(
            vault_folder=str(tmp_path), template_file=str(tpl_file)
        )
        audio_path = tmp_path / "recording.m4a"
        audio_path.touch()

        output = render_and_write(note_data, audio_path, config)

        content = output.read_text(encoding="utf-8")
        assert content.startswith("CUSTOM:Test Note")

    def test_missing_template_file_raises_runtime_error(self, tmp_path: Path):
        note_data = _make_note_data()
        config = _make_full_config(
            vault_folder=str(tmp_path),
            template_file="/does/not/exist.j2",
        )
        audio_path = tmp_path / "recording.m4a"
        audio_path.touch()

        with pytest.raises(RuntimeError, match="template load"):
            render_and_write(note_data, audio_path, config)

    def test_output_filename_contains_date_and_title(self, tmp_path: Path):
        note_data = _make_note_data(
            title="My Meeting",
            recorded_at=datetime(2026, 4, 20, 14, 30, 0),
        )
        config = _make_full_config(vault_folder=str(tmp_path))
        audio_path = tmp_path / "recording.m4a"
        audio_path.touch()

        output = render_and_write(note_data, audio_path, config)

        assert "2026-04-20" in output.name
        assert "My Meeting" in output.name
        assert output.suffix == ".md"

    def test_subfolder_pattern_creates_correct_directory(self, tmp_path: Path):
        note_data = _make_note_data(recorded_at=datetime(2026, 4, 20, 14, 30, 0))
        config = _make_full_config(vault_folder=str(tmp_path))
        config["note"]["subfolder_pattern"] = "{year}/{month}"
        audio_path = tmp_path / "recording.m4a"
        audio_path.touch()

        output = render_and_write(note_data, audio_path, config)

        assert output.parent == tmp_path / "2026" / "04"
        assert output.exists()

    def test_transcript_included_in_note_when_enabled(self, tmp_path: Path):
        note_data = _make_note_data(
            transcript="This is the full transcript text.",
            recorded_at=datetime(2026, 4, 20, 14, 30, 0),
        )
        config = _make_full_config(vault_folder=str(tmp_path))
        config["note"]["include_full_transcript"] = True
        config["note"]["collapse_transcript"] = False
        audio_path = tmp_path / "recording.m4a"
        audio_path.touch()

        output = render_and_write(note_data, audio_path, config)

        content = output.read_text(encoding="utf-8")
        assert "This is the full transcript text." in content

    def test_transcript_omitted_when_disabled(self, tmp_path: Path):
        note_data = _make_note_data(
            transcript="Should not appear.",
            recorded_at=datetime(2026, 4, 20, 14, 30, 0),
        )
        config = _make_full_config(vault_folder=str(tmp_path))
        config["note"]["include_full_transcript"] = False
        audio_path = tmp_path / "recording.m4a"
        audio_path.touch()

        output = render_and_write(note_data, audio_path, config)

        content = output.read_text(encoding="utf-8")
        assert "Should not appear." not in content

    def test_collapse_transcript_wraps_in_details_tag(self, tmp_path: Path):
        note_data = _make_note_data(
            transcript="Collapsible content.",
            recorded_at=datetime(2026, 4, 20, 14, 30, 0),
        )
        config = _make_full_config(vault_folder=str(tmp_path))
        config["note"]["include_full_transcript"] = True
        config["note"]["collapse_transcript"] = True
        audio_path = tmp_path / "recording.m4a"
        audio_path.touch()

        output = render_and_write(note_data, audio_path, config)

        content = output.read_text(encoding="utf-8")
        assert "<details>" in content
        assert "Collapsible content." in content

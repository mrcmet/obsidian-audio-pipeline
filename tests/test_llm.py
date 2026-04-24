"""
tests/test_llm.py — Unit tests for llm.py parsing and prompt construction.

Tests cover _parse_llm_response (all parsing paths, validation, defaults)
and build_system_prompt (content requirements). No LLM backends are called;
no network or API interaction occurs.
"""

from __future__ import annotations

import json

import pytest

from llm import _parse_llm_response, build_system_prompt


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _valid_json(**overrides) -> str:
    """Return a minimal valid JSON string as the LLM would produce it."""
    base = {
        "title": "Team Standup",
        "summary": "Quick status update.",
        "key_points": ["All green", "Deploy Friday"],
        "todos": [{"task": "Write tests", "owner": "Alice", "due": "2026-04-25"}],
        "decisions": ["Deploy on Friday"],
        "attendees": ["Alice Smith"],
        "follow_ups": ["Check staging"],
        "tags": ["meeting", "standup"],
        "custom_sections": {},
    }
    base.update(overrides)
    return json.dumps(base)


# ---------------------------------------------------------------------------
# _parse_llm_response — valid inputs
# ---------------------------------------------------------------------------


class TestParseLlmResponseValidInputs:
    def test_valid_json_returns_correct_dict(self):
        result = _parse_llm_response(_valid_json())
        assert result["title"] == "Team Standup"
        assert result["summary"] == "Quick status update."
        assert result["tags"] == ["meeting", "standup"]
        assert len(result["todos"]) == 1
        assert result["todos"][0]["task"] == "Write tests"

    def test_json_in_backtick_fences_parsed(self):
        fenced = "```json\n" + _valid_json() + "\n```"
        result = _parse_llm_response(fenced)
        assert result["title"] == "Team Standup"

    def test_json_in_plain_backtick_fences_parsed(self):
        fenced = "```\n" + _valid_json() + "\n```"
        result = _parse_llm_response(fenced)
        assert result["title"] == "Team Standup"

    def test_think_block_stripped_before_parsing(self):
        raw = "<think>Let me analyse this carefully.</think>\n" + _valid_json()
        result = _parse_llm_response(raw)
        assert result["title"] == "Team Standup"

    def test_think_block_case_insensitive_stripped(self):
        raw = "<THINK>Some internal reasoning</THINK>\n" + _valid_json()
        result = _parse_llm_response(raw)
        assert result["title"] == "Team Standup"

    def test_prose_before_json_block_extracted_with_result(self):
        raw = "Here is my analysis:\n\nSome intro prose.\n\n" + _valid_json()
        result = _parse_llm_response(raw)
        assert result["title"] == "Team Standup"

    def test_raw_llm_response_preserved_in_result(self):
        raw = _valid_json()
        result = _parse_llm_response(raw)
        assert result["raw_llm_response"] == raw


# ---------------------------------------------------------------------------
# _parse_llm_response — invalid inputs and error handling
# ---------------------------------------------------------------------------


class TestParseLlmResponseInvalidInputs:
    def test_invalid_json_raises_runtime_error(self):
        with pytest.raises(RuntimeError, match="invalid JSON"):
            _parse_llm_response("this is not json at all")

    def test_empty_string_raises_runtime_error(self):
        with pytest.raises(RuntimeError):
            _parse_llm_response("")

    def test_json_array_raises_runtime_error(self):
        with pytest.raises(RuntimeError, match="expected an object"):
            _parse_llm_response("[1, 2, 3]")


# ---------------------------------------------------------------------------
# _parse_llm_response — missing fields get safe defaults
# ---------------------------------------------------------------------------


class TestParseLlmResponseDefaults:
    def test_missing_title_defaults_to_untitled(self):
        raw = json.dumps({"summary": "A summary."})
        result = _parse_llm_response(raw)
        assert result["title"] == "Untitled Note"

    def test_blank_title_defaults_to_untitled(self):
        raw = json.dumps({"title": "   ", "summary": "S"})
        result = _parse_llm_response(raw)
        assert result["title"] == "Untitled Note"

    def test_missing_list_fields_default_to_empty_list(self):
        raw = json.dumps({"title": "T", "summary": "S"})
        result = _parse_llm_response(raw)
        for field in ("key_points", "decisions", "attendees", "follow_ups", "tags"):
            assert result[field] == [], f"Expected empty list for {field}"

    def test_missing_todos_defaults_to_empty_list(self):
        raw = json.dumps({"title": "T"})
        result = _parse_llm_response(raw)
        assert result["todos"] == []

    def test_missing_custom_sections_defaults_to_empty_dict(self):
        raw = json.dumps({"title": "T"})
        result = _parse_llm_response(raw)
        assert result["custom_sections"] == {}


# ---------------------------------------------------------------------------
# _parse_llm_response — field-level cleaning
# ---------------------------------------------------------------------------


class TestParseLlmResponseFieldCleaning:
    def test_tags_with_hash_prefix_stripped(self):
        raw = json.dumps({"title": "T", "tags": ["#meeting", "#notes", "clean"]})
        result = _parse_llm_response(raw)
        assert result["tags"] == ["meeting", "notes", "clean"]

    def test_empty_tags_after_hash_strip_dropped(self):
        # A tag that is only "#" should be dropped.
        raw = json.dumps({"title": "T", "tags": ["#", "real-tag"]})
        result = _parse_llm_response(raw)
        assert "#" not in result["tags"]
        assert "real-tag" in result["tags"]

    def test_todo_with_empty_task_dropped(self):
        raw = json.dumps({
            "title": "T",
            "todos": [
                {"task": "", "owner": "Alice", "due": None},
                {"task": "Valid task", "owner": "Bob", "due": None},
            ],
        })
        result = _parse_llm_response(raw)
        assert len(result["todos"]) == 1
        assert result["todos"][0]["task"] == "Valid task"

    def test_todo_with_whitespace_only_task_dropped(self):
        raw = json.dumps({
            "title": "T",
            "todos": [{"task": "   ", "owner": "", "due": None}],
        })
        result = _parse_llm_response(raw)
        assert result["todos"] == []

    def test_todo_non_dict_items_dropped(self):
        raw = json.dumps({
            "title": "T",
            "todos": [
                "not a dict",
                {"task": "Real task", "owner": "", "due": None},
            ],
        })
        result = _parse_llm_response(raw)
        assert len(result["todos"]) == 1

    def test_custom_sections_as_non_dict_defaults_to_empty(self):
        raw = json.dumps({"title": "T", "custom_sections": ["not", "a", "dict"]})
        result = _parse_llm_response(raw)
        assert result["custom_sections"] == {}

    def test_todo_due_none_preserved(self):
        raw = json.dumps({
            "title": "T",
            "todos": [{"task": "Do it", "owner": "", "due": None}],
        })
        result = _parse_llm_response(raw)
        assert result["todos"][0]["due"] is None

    def test_todo_due_non_string_coerced_to_string(self):
        raw = json.dumps({
            "title": "T",
            "todos": [{"task": "Do it", "owner": "", "due": 20260425}],
        })
        result = _parse_llm_response(raw)
        assert isinstance(result["todos"][0]["due"], str)

    def test_tags_comma_string_split_when_model_returns_string(self):
        # Some models return a comma-separated string instead of a list.
        raw = json.dumps({"title": "T", "tags": "meeting, standup, notes"})
        result = _parse_llm_response(raw)
        assert "meeting" in result["tags"]
        assert "standup" in result["tags"]
        assert "notes" in result["tags"]


# ---------------------------------------------------------------------------
# build_system_prompt
# ---------------------------------------------------------------------------


def _make_config(custom_instructions: str = "") -> dict:
    return {
        "note": {
            "custom_prompt_instructions": custom_instructions,
            "fallback_tags": ["meeting", "notes"],
        }
    }


class TestBuildSystemPrompt:
    def test_prompt_contains_json_keyword(self):
        prompt = build_system_prompt(_make_config(), vault_tags=[])
        assert "JSON" in prompt

    def test_vault_tags_appear_in_prompt(self):
        tags = ["meeting", "project-x", "q3-planning"]
        prompt = build_system_prompt(_make_config(), vault_tags=tags)
        for tag in tags:
            assert tag in prompt

    def test_empty_vault_tags_shows_fallback_message(self):
        prompt = build_system_prompt(_make_config(), vault_tags=[])
        assert "No existing vault tags" in prompt

    def test_custom_prompt_instructions_appear_in_prompt(self):
        instructions = "Write all summaries as bullet points."
        prompt = build_system_prompt(
            _make_config(custom_instructions=instructions), vault_tags=[]
        )
        assert instructions in prompt

    def test_empty_custom_instructions_not_added(self):
        prompt = build_system_prompt(_make_config(custom_instructions=""), vault_tags=[])
        assert "Additional instructions" not in prompt

    def test_prompt_describes_expected_schema_fields(self):
        prompt = build_system_prompt(_make_config(), vault_tags=[])
        for field in ("title", "summary", "todos", "tags", "decisions"):
            assert field in prompt

    def test_large_vault_tag_list_truncated(self):
        # 400 tags — only first 300 should appear in the prompt.
        tags = [f"tag-{i}" for i in range(400)]
        prompt = build_system_prompt(_make_config(), vault_tags=tags)
        # tag-300 should NOT appear; tag-0 should.
        assert "tag-0" in prompt
        assert "tag-300" not in prompt

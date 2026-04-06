"""
llm.py — Transcript → structured note data via LLM.

Supports three backends: anthropic, openai, ollama.

Public interface:
    extract_note_data(transcript, duration, audio_path, config) -> dict

All config flows in as a parameter dict; nothing is imported globally.
"""

import json
import logging
import os
import re
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# System prompt construction
# ---------------------------------------------------------------------------

_JSON_SCHEMA = """{
  "title": "Short descriptive title (5–10 words)",
  "summary": "3–5 sentence or bullet-point overview of the recording",
  "key_points": ["Main takeaway 1", "Main takeaway 2"],
  "todos": [
    {"task": "Task description", "owner": "Person responsible", "due": null}
  ],
  "decisions": ["Concrete decision made during the recording"],
  "attendees": ["Full name of each person mentioned or speaking"],
  "follow_ups": ["Soft next step or parking-lot item"],
  "tags": ["obsidian-tag-name"],
  "custom_sections": {}
}"""


def build_system_prompt(config: dict, vault_tags: list[str]) -> str:
    """
    Construct the LLM system prompt.

    Includes: role description, strict JSON output instructions, the JSON
    schema, vault tag guidance (if tags are available), and any
    custom_prompt_instructions from config.
    """
    parts: list[str] = []

    parts.append(
        "You are an expert note-taker that extracts structured information from "
        "audio recording transcripts — meetings, voice memos, and lectures.\n\n"
        "Your task is to analyse the transcript provided by the user and return "
        "ONLY a single valid JSON object. Do not include any explanation, "
        "commentary, markdown prose, or additional text outside the JSON. "
        "Do not wrap the JSON in code fences."
    )

    parts.append(
        "The JSON object must conform exactly to this schema:\n"
        + _JSON_SCHEMA
        + "\n\n"
        "Field rules:\n"
        "- title: concise, descriptive, 5–10 words.\n"
        "- summary: 3–5 sentences or bullet points summarising the recording.\n"
        "- key_points: the most important takeaways as a list of strings.\n"
        "- todos: action items. Set owner to an empty string if unknown. "
        "Set due to null if no date was mentioned.\n"
        "- decisions: concrete conclusions or agreements reached — distinct from action items.\n"
        "- attendees: full names of every person mentioned or heard speaking.\n"
        "- follow_ups: soft next steps, parking-lot items, or unresolved questions.\n"
        "- tags: Obsidian tag names, lowercase with hyphens, no # prefix.\n"
        "- custom_sections: an object whose keys are section headings and values "
        "are the section content (markdown string). Leave as {} if not needed."
    )

    if vault_tags:
        # Truncate to a reasonable size to avoid ballooning the prompt context.
        display_tags = vault_tags[:300]
        tag_list = ", ".join(display_tags)
        truncation_note = (
            f" (showing {len(display_tags)} of {len(vault_tags)})"
            if len(vault_tags) > len(display_tags)
            else ""
        )
        parts.append(
            f"The following tags already exist in the Obsidian vault{truncation_note}. "
            "Prefer choosing tags from this list when they are relevant. "
            "You may introduce new tags only when none of the existing ones fit:\n"
            f"{tag_list}"
        )
    else:
        parts.append(
            "No existing vault tags were found. Choose appropriate lowercase, "
            "hyphen-separated tag names that suit the content."
        )

    custom_instructions = config.get("note", {}).get("custom_prompt_instructions", "").strip()
    if custom_instructions:
        parts.append(
            "Additional instructions — follow these precisely:\n" + custom_instructions
        )

    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------

def _parse_llm_response(raw: str) -> dict:
    """
    Parse the raw LLM response string into a validated note_data dict.

    Handles:
    - Markdown code fences (```json ... ```)
    - Leading/trailing whitespace and prose before/after the JSON block
    - Missing or wrongly-typed fields (safe defaults applied per field)

    Raises RuntimeError if valid JSON cannot be extracted.
    """
    text = raw.strip()

    # Strip markdown code fences: ```json ... ``` or ``` ... ```
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text)
    text = text.strip()

    # If the LLM included prose before or after the JSON object, extract the
    # first {...} block. This is a resilience measure for non-compliant models.
    if not text.startswith("{"):
        match = re.search(r"\{[\s\S]*\}", text)
        if match:
            logger.warning(
                "LLM response contained text outside the JSON block; "
                "extracted JSON object from position %d", match.start()
            )
            text = match.group(0)

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        logger.error(
            "Failed to parse LLM response as JSON. Error: %s\nRaw response:\n%s",
            exc,
            raw,
        )
        raise RuntimeError(
            f"LLM returned invalid JSON: {exc}. "
            "Check raw_llm_response in the log for the full output."
        ) from exc

    if not isinstance(parsed, dict):
        logger.error(
            "LLM response parsed as %s, expected dict. Raw response:\n%s",
            type(parsed).__name__,
            raw,
        )
        raise RuntimeError(
            f"LLM JSON parsed as {type(parsed).__name__}, expected an object/dict."
        )

    # Safe defaults — every field guaranteed to be present and correctly typed.
    defaults: dict = {
        "title": "Untitled Note",
        "summary": "",
        "key_points": [],
        "todos": [],
        "decisions": [],
        "attendees": [],
        "follow_ups": [],
        "tags": [],
        "custom_sections": {},
    }

    result: dict = {}

    # --- str fields ---
    for field in ("title", "summary"):
        value = parsed.get(field, defaults[field])
        result[field] = value if isinstance(value, str) else str(value)

    # Ensure title is never blank after coercion.
    if not result["title"].strip():
        result["title"] = defaults["title"]

    # --- list[str] fields ---
    for field in ("key_points", "decisions", "attendees", "follow_ups", "tags"):
        raw_value = parsed.get(field, defaults[field])
        if isinstance(raw_value, list):
            # Coerce each element to str, drop empties.
            result[field] = [str(item) for item in raw_value if item is not None]
        elif isinstance(raw_value, str) and raw_value.strip():
            # Some models return a comma-separated string instead of a list.
            result[field] = [s.strip() for s in raw_value.split(",") if s.strip()]
        else:
            result[field] = defaults[field]

    # Strip '#' prefix from tags — Obsidian tags stored without it.
    result["tags"] = [t.lstrip("#").strip() for t in result["tags"] if t.lstrip("#").strip()]

    # --- list[dict] (todos) ---
    raw_todos = parsed.get("todos", [])
    if isinstance(raw_todos, list):
        validated_todos: list[dict] = []
        for item in raw_todos:
            if not isinstance(item, dict):
                continue
            todo: dict = {
                "task": str(item.get("task", "")).strip(),
                "owner": str(item.get("owner", "")).strip(),
                "due": item.get("due"),
            }
            # due must be a string or None.
            if todo["due"] is not None and not isinstance(todo["due"], str):
                todo["due"] = str(todo["due"])
            if todo["task"]:  # Drop todos with no task text.
                validated_todos.append(todo)
        result["todos"] = validated_todos
    else:
        result["todos"] = defaults["todos"]

    # --- dict (custom_sections) ---
    raw_sections = parsed.get("custom_sections", {})
    if isinstance(raw_sections, dict):
        result["custom_sections"] = {
            str(k): str(v) for k, v in raw_sections.items()
        }
    else:
        result["custom_sections"] = defaults["custom_sections"]

    result["raw_llm_response"] = raw

    return result


# ---------------------------------------------------------------------------
# LLM backends
# ---------------------------------------------------------------------------

def _call_anthropic(system_prompt: str, user_prompt: str, cfg: dict) -> str:
    """
    Call the Anthropic Messages API.

    Reads the API key from the environment variable named by cfg["api_key_env"].
    Raises RuntimeError on configuration errors or API failures.
    """
    try:
        from anthropic import Anthropic  # type: ignore[import-untyped]
    except ImportError as exc:
        raise RuntimeError(
            "The 'anthropic' package is not installed. "
            "Run: pip install anthropic"
        ) from exc

    key_env = cfg.get("api_key_env", "ANTHROPIC_API_KEY")
    api_key = os.environ.get(key_env)
    if not api_key:
        raise RuntimeError(
            f"Anthropic API key not set. "
            f"Export the environment variable '{key_env}' before running the pipeline."
        )

    model = cfg.get("model", "claude-3-5-sonnet-20241022")
    logger.debug("Calling Anthropic API with model '%s'", model)

    try:
        client = Anthropic(api_key=api_key)
        response = client.messages.create(
            model=model,
            max_tokens=4096,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        return response.content[0].text
    except Exception as exc:
        logger.error("Anthropic API call failed: %s", exc)
        raise RuntimeError(f"Anthropic API call failed: {exc}") from exc


def _call_openai(system_prompt: str, user_prompt: str, cfg: dict) -> str:
    """
    Call the OpenAI Chat Completions API.

    Reads the API key from the environment variable named by cfg["api_key_env"].
    Raises RuntimeError on configuration errors or API failures.
    """
    try:
        from openai import OpenAI  # type: ignore[import-untyped]
    except ImportError as exc:
        raise RuntimeError(
            "The 'openai' package is not installed. "
            "Run: pip install openai"
        ) from exc

    key_env = cfg.get("api_key_env", "OPENAI_API_KEY")
    api_key = os.environ.get(key_env)
    if not api_key:
        raise RuntimeError(
            f"OpenAI API key not set. "
            f"Export the environment variable '{key_env}' before running the pipeline."
        )

    model = cfg.get("model", "gpt-4o")
    logger.debug("Calling OpenAI API with model '%s'", model)

    try:
        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model=model,
            max_tokens=4096,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        return response.choices[0].message.content
    except Exception as exc:
        logger.error("OpenAI API call failed: %s", exc)
        raise RuntimeError(f"OpenAI API call failed: {exc}") from exc


def _call_ollama(system_prompt: str, user_prompt: str, cfg: dict) -> str:
    """
    Call a locally running Ollama instance via its HTTP API.

    Uses only stdlib (urllib) — no extra dependencies required.
    Raises RuntimeError if Ollama is unreachable or returns an error response.
    """
    model = cfg.get("model", "llama3.1")
    base_url = cfg.get("base_url", "http://localhost:11434")
    endpoint = f"{base_url.rstrip('/')}/api/chat"

    payload = {
        "model": model,
        "stream": False,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }

    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        endpoint,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    logger.debug("Calling Ollama at %s with model '%s'", endpoint, model)

    try:
        with urllib.request.urlopen(request, timeout=300) as resp:
            raw_bytes = resp.read()
    except urllib.error.URLError as exc:
        logger.error("Cannot reach Ollama at %s: %s", endpoint, exc)
        raise RuntimeError(
            f"Cannot reach Ollama at {endpoint}. "
            "Ensure Ollama is installed and running ('ollama serve'). "
            f"Error: {exc}"
        ) from exc
    except Exception as exc:
        logger.error("Ollama request failed: %s", exc)
        raise RuntimeError(f"Ollama request failed: {exc}") from exc

    try:
        data = json.loads(raw_bytes.decode("utf-8"))
    except json.JSONDecodeError as exc:
        logger.error("Ollama returned non-JSON response: %s", raw_bytes[:500])
        raise RuntimeError(f"Ollama returned non-JSON response: {exc}") from exc

    # Ollama may return an error field at the top level.
    if "error" in data:
        logger.error("Ollama returned error: %s", data["error"])
        raise RuntimeError(f"Ollama error: {data['error']}")

    try:
        return data["message"]["content"]
    except (KeyError, TypeError) as exc:
        logger.error("Unexpected Ollama response structure: %s", data)
        raise RuntimeError(
            f"Unexpected Ollama response structure — missing 'message.content': {exc}"
        ) from exc


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

def extract_note_data(
    transcript: str,
    duration: float | None,
    audio_path: Path,
    config: dict,
) -> dict:
    """
    Send transcript to an LLM and extract structured note data.

    Parameters
    ----------
    transcript:  Plain-text transcript produced by transcriber.py.
    duration:    Recording duration in seconds, or None if unknown.
    audio_path:  Path to the original audio file (used for filename and mtime).
    config:      Full config dict from config.py (passed down, never imported).

    Returns
    -------
    dict matching the note_data schema (see architecture.md).

    Raises
    ------
    ValueError      Unknown backend name.
    RuntimeError    API/network failure or unparseable LLM response.
    """
    llm_cfg = config.get("llm", {})
    backend = llm_cfg.get("backend", "anthropic")

    # Vault tags — failures are non-fatal; fall back to config list.
    from vault_tags import get_vault_tags  # noqa: PLC0415 — intentional local import

    try:
        vault_tags = get_vault_tags(config.get("obsidian_vault_folder", ""))
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Could not load vault tags (%s); falling back to config fallback_tags.", exc
        )
        vault_tags = config.get("note", {}).get("fallback_tags", [])

    system_prompt = build_system_prompt(config, vault_tags)

    # Build the user prompt with enough context for the LLM.
    if duration is not None:
        minutes = int(duration // 60)
        seconds = int(duration % 60)
        duration_str = f"{minutes}m {seconds}s"
    else:
        duration_str = "unknown"

    user_prompt = (
        f"Audio file: {audio_path.name}\n"
        f"Duration: {duration_str}\n\n"
        f"Transcript:\n{transcript}"
    )

    logger.info(
        "Extracting note data via '%s' backend for '%s'", backend, audio_path.name
    )

    if backend == "anthropic":
        raw = _call_anthropic(system_prompt, user_prompt, llm_cfg)
    elif backend == "openai":
        raw = _call_openai(system_prompt, user_prompt, llm_cfg)
    elif backend == "ollama":
        raw = _call_ollama(system_prompt, user_prompt, llm_cfg)
    else:
        raise ValueError(
            f"Unknown LLM backend: {backend!r}. "
            "Valid options are: 'anthropic', 'openai', 'ollama'."
        )

    logger.debug("Raw LLM response (%d chars) received", len(raw))

    note_data = _parse_llm_response(raw)

    # Derive recorded_at from the audio file's modification time.
    # If the file has already been moved/deleted (e.g. archive ran first), fall
    # back to the current time so downstream stages always have a datetime.
    try:
        note_data["recorded_at"] = datetime.fromtimestamp(audio_path.stat().st_mtime)
    except OSError as exc:
        logger.warning(
            "Could not stat '%s' for mtime (%s); using current time as recorded_at.",
            audio_path,
            exc,
        )
        note_data["recorded_at"] = datetime.now()

    logger.info(
        "Note data extracted: title='%s', tags=%s, todos=%d, decisions=%d",
        note_data["title"],
        note_data["tags"],
        len(note_data["todos"]),
        len(note_data["decisions"]),
    )

    return note_data

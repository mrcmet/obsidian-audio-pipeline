# Obsidian Audio Pipeline

A Python background service that watches a folder for audio files, transcribes them,
and writes structured Obsidian-ready markdown notes using an LLM.

## What This Is

Voice memos and meeting recordings dropped into a watch folder automatically become
formatted Obsidian notes — with summary, tags drawn from the live vault, action items,
decisions, and a collapsible full transcript.

## Key Docs — Read Before Working

Before making changes, check which of these is relevant to your task:

- @docs/architecture.md     — module map, data flow, where things live
- @docs/building.md         — how to install, run, test, and debug
- @docs/implementation-plan.md — phased build plan with open tasks (checkboxes)
- @docs/customization.md    — how the LLM prompt and Jinja2 template system works

## Commands

```bash
# Install
python -m venv venv && source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Run
python main.py

# Test a single file without the watcher
python -c "from pipeline import run_pipeline; from pathlib import Path; from config import load_config; run_pipeline(Path('test.m4a'), load_config())"

# Manually refresh vault tags (for debugging)
python -c "from vault_tags import get_vault_tags; print(get_vault_tags('~/Documents/Obsidian'))"
```

## Conventions

- All pipeline stages are **independent modules** — `transcriber.py`, `llm.py`, `note_writer.py`.
  Keep them that way. No cross-imports between stages.
- Config always flows **downward** — modules receive the config dict as a parameter, never import it globally.
- New LLM backends go in `llm.py` following the `_call_<backend>` pattern.
- New transcription backends go in `transcriber.py` following the `_transcribe_<backend>` pattern.
- The **only** place to change note structure is `llm.py` (JSON schema) and `note_writer.py` (template).
- Errors in any pipeline stage should **log and raise** — never silently swallow.
- Python 3.11+ required (uses `X | Y` union types).

## Environment Variables

| Variable | Used by |
|---|---|
| `ANTHROPIC_API_KEY` | llm.py when backend = anthropic |
| `OPENAI_API_KEY` | llm.py when backend = openai, transcriber.py when backend = openai-api |

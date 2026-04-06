# Architecture

## Module Map

```
obsidian-audio-pipeline/
├── main.py           Entry point. Loads config, starts watcher.
├── config.py         Loads config.yaml, deep-merges with defaults.
├── watcher.py        watchdog FileSystemEventHandler. Detects new audio files,
│                     waits for file stability, calls run_pipeline().
├── pipeline.py       Orchestrator. Calls transcriber → llm → note_writer → cleanup.
├── transcriber.py    Audio → plain text transcript + duration.
├── llm.py            Transcript → structured JSON via LLM. Primary customization point.
├── note_writer.py    JSON + Jinja2 template → .md file written to vault.
├── vault_tags.py     Scans vault .md files for all unique tags (cached).
├── config.yaml       User configuration (edit this, not config.py).
├── requirements.txt  Python dependencies.
└── docs/             Reference docs for Claude Code sessions.
```

## Data Flow

```
Audio file lands in watch_folder
        │
        ▼
watcher.py — polls until file size is stable (fully written)
        │
        ▼
pipeline.run_pipeline(audio_path, config)
        │
        ├─▶ transcriber.transcribe()
        │     Returns: (transcript: str, duration_seconds: float | None)
        │     Backends: faster-whisper (local) | openai-api (cloud)
        │
        ├─▶ llm.extract_note_data()
        │     Builds system prompt (with live vault tags from vault_tags.py)
        │     Sends transcript to LLM
        │     Parses JSON response
        │     Returns: note_data dict (see schema below)
        │
        ├─▶ note_writer.render_and_write()
        │     Feeds note_data into Jinja2 template
        │     Resolves output path (vault folder + subfolder_pattern + dated title)
        │     Writes .md file
        │     Returns: Path to written note
        │
        └─▶ _handle_audio_file()
              archive | delete | leave
```

## note_data Schema

The dict returned by `llm.extract_note_data()` and consumed by `note_writer`:

```python
{
    "title":           str,           # Short descriptive title
    "summary":         str,           # 3-5 sentence / bullet overview
    "key_points":      list[str],     # Main takeaways
    "todos":           list[dict],    # {task: str, owner: str, due: str | None}
    "decisions":       list[str],     # Concrete decisions made
    "attendees":       list[str],     # Names mentioned
    "follow_ups":      list[str],     # Parking lot / soft next steps
    "tags":            list[str],     # Obsidian tags (no # prefix)
    "custom_sections": dict,          # {section_name: content} for extra LLM sections
    "recorded_at":     datetime,      # Derived from file mtime
    "raw_llm_response": str,          # Raw LLM output, for debugging
}
```

## Config Schema (key fields)

```yaml
watch_folder:           str   # Folder to monitor
obsidian_vault_folder:  str   # Vault inbox folder (also used for tag scanning)
archive_folder:         str   # Where processed audio files go

transcriber:
  backend:   faster-whisper | openai-api
  model:     str   # Whisper model size
  language:  str | null
  device:    cpu | cuda | auto

llm:
  backend:   anthropic | openai | ollama
  model:     str
  api_key_env: str   # Name of env var holding the key

note:
  template_file:              str   # Path to custom .j2 template (optional)
  fallback_tags:              list  # Used if vault scan fails
  custom_prompt_instructions: str   # Freeform rules injected into LLM system prompt
  include_full_transcript:    bool
  collapse_transcript:        bool
  subfolder_pattern:          str   # e.g. "{year}/{month}"

on_complete:
  audio_file_action: archive | delete | leave
```

## Tag Scanning (vault_tags.py)

- Scans all `.md` files under `obsidian_vault_folder` recursively
- Reads both YAML frontmatter tags and inline `#hashtags`
- Skips `.obsidian/` system folders
- Results are **cached in-process** — no re-scan per audio file
- Falls back to `note.fallback_tags` in config if vault is unreachable

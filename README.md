# Obsidian Audio Pipeline

A Python background service that turns audio files into structured Obsidian notes — automatically.

![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)
![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS-lightgrey)
![License](https://img.shields.io/badge/license-MIT-green)

---

## Table of Contents

- [What It Does](#what-it-does)
- [Features](#features)
- [Quick Start](#quick-start)
- [Requirements](#requirements)
- [Configuration](#configuration)
- [LLM Backends](#llm-backends)
- [Transcription Backends](#transcription-backends)
- [Customization](#customization)
- [Running as a Service](#running-as-a-service)
- [Project Structure](#project-structure)
- [Contributing](#contributing)
- [Known Limitations](#known-limitations)
- [License](#license)

---

## What It Does

Drop a voice memo or meeting recording into a watch folder. A formatted Obsidian note appears in your vault within seconds.

```
Audio file (.m4a / .mp3 / .wav)
        |
        v
   Whisper (local or cloud)  →  plain-text transcript
        |
        v
   LLM (Claude / GPT / Ollama)  →  summary, action items, decisions, tags
        |
        v
   Jinja2 template  →  .md note written to your vault
```

Tags are drawn from your live vault so every note slots into your existing taxonomy. The full transcript is appended in a collapsible block.

![PLACEHOLDER: Screenshot of a generated Obsidian note showing frontmatter, summary, action items, and collapsed transcript](docs/images/sample-note.png)

---

## Features

- **Local transcription** via faster-whisper or WhisperX — no audio leaves your machine
- **Cloud transcription** via OpenAI Whisper API for zero-GPU setups
- **Speaker diarization** — WhisperX + pyannote labels each speaker turn
- **Any LLM backend** — Anthropic Claude, OpenAI GPT, or local Ollama (no API key)
- **Live vault tag scanning** — tags are pulled from your actual `.md` files, not a hardcoded list
- **System tray app** — Start, Stop, Restart, and view logs from a menu bar icon; no terminal required
- **Settings GUI** — tabbed editor for all config options; no need to hand-edit YAML
- **Custom Jinja2 templates** — full control over note layout
- **Startup registration** — one command registers the tray app to launch at login
- **Structured note schema** — title, summary, key points, action items, decisions, attendees, follow-ups, full transcript

---

## Quick Start

```bash
# 1. Clone the repo
$ git clone https://github.com/YOUR_USERNAME/obsidian-audio-pipeline.git
$ cd obsidian-audio-pipeline

# 2. Create and activate a virtual environment
$ python -m venv venv
$ source venv/bin/activate        # Mac / Linux
# venv\Scripts\activate           # Windows

# 3. Install dependencies (auto-detects NVIDIA GPU)
$ python install.py

# 4. Set your LLM API key (skip if using Ollama)
$ export ANTHROPIC_API_KEY="YOUR_ANTHROPIC_API_KEY"

# 5. Edit the two required lines in config.yaml
#    watch_folder: ~/Desktop/AudioDrop
#    obsidian_vault_folder: ~/Documents/Obsidian/Inbox

# 6. Launch the tray app
$ python tray.py
```

A tray icon appears. Drop any audio file into your `watch_folder`. The note appears in your vault within 10–60 seconds.

> **💡 Tip:** The first run downloads the Whisper model weights (~1.6 GB for the default `large-v3-turbo`). This looks like it is hanging — check `pipeline.log` for download progress.

---

## Requirements

| Dependency | Version | Notes |
|---|---|---|
| Python | 3.11+ | Uses `X \| Y` union types |
| NVIDIA GPU | Optional | Required for `cuda` device; CPU works but is slower |
| VRAM | 6 GB+ (recommended) | `large-v3-turbo` needs ~6 GB; `tiny` runs on ~1 GB |
| Anthropic API key | — | Only for `anthropic` LLM backend |
| OpenAI API key | — | Only for `openai` LLM backend or `openai-api` transcriber |
| Ollama | Any recent | Only for `ollama` LLM backend; run `ollama serve` first |
| HuggingFace token | — | Only for speaker diarization (whisperx backend) |

---

## Configuration

Open `config.yaml`. Two fields are required — everything else has sensible defaults.

```yaml
watch_folder: ~/Desktop/AudioDrop          # REQUIRED: create this folder
obsidian_vault_folder: ~/Documents/Obsidian/Inbox  # REQUIRED: must exist in your vault
```

### Key options

| Option | Default | Description |
|---|---|---|
| `watch_folder` | — | Folder to watch for incoming audio files |
| `obsidian_vault_folder` | — | Vault inbox folder; also used for tag scanning |
| `archive_folder` | `~/Desktop/AudioDrop/processed` | Where processed audio files move (if `archive` action is set) |
| `transcriber.backend` | `whisperx` | `faster-whisper`, `whisperx`, or `openai-api` |
| `transcriber.model` | `large-v3-turbo` | Whisper model size: `tiny`, `base`, `small`, `medium`, `large-v3-turbo`, `large-v3` |
| `transcriber.device` | `auto` | `auto`, `cpu`, or `cuda` |
| `transcriber.compute_type` | `float16` | `float16` (GPU), `int8` (low VRAM), or `float32` |
| `transcriber.batch_size` | `16` | Reduce to `8` if you see VRAM out-of-memory errors |
| `transcriber.diarization.enabled` | `false` | Enable speaker labeling (whisperx only) |
| `llm.backend` | `ollama` | `anthropic`, `openai`, or `ollama` |
| `llm.model` | `qwen3:32b` | Model name for the chosen backend |
| `note.template_file` | `templates/obsidian_note.j2` | Path to a custom Jinja2 template (`null` = built-in default) |
| `note.include_full_transcript` | `true` | Append the full transcript to the note |
| `note.collapse_transcript` | `true` | Wrap transcript in a `<details>` collapse block |
| `note.subfolder_pattern` | `""` | Subfolder inside vault folder — supports `{year}`, `{month}`, `{day}` |
| `note.custom_prompt_instructions` | `""` | Free-form instructions appended to the LLM system prompt |
| `note.fallback_tags` | `[meeting, notes, audio]` | Tags used when vault scanning fails |
| `on_complete.audio_file_action` | `leave` | What to do with the source audio: `archive`, `delete`, or `leave` |

---

## LLM Backends

| Backend | Model example | Env var to set |
|---|---|---|
| `anthropic` | `claude-opus-4-6` | `ANTHROPIC_API_KEY` |
| `openai` | `gpt-4o` | `OPENAI_API_KEY` |
| `ollama` | `llama3.1`, `qwen3:32b` | None — run `ollama serve` locally |

Set the backend in `config.yaml`:

```yaml
llm:
  backend: anthropic
  model: claude-3-5-sonnet-20241022
```

The API key is read from the environment at runtime — never put it in `config.yaml`.

---

## Transcription Backends

| Backend | How it runs | GPU required | Diarization |
|---|---|---|---|
| `faster-whisper` | Local, CTranslate2-accelerated | No (CPU works) | No |
| `whisperx` | Local, word-aligned segments | Recommended | Yes (pyannote 3.1) |
| `openai-api` | Cloud (OpenAI Whisper endpoint) | No | No |

### Whisper model sizes

| Model | VRAM | Speed | Accuracy |
|---|---|---|---|
| `tiny` / `base` | ~1 GB | Fastest | Lower |
| `small` | ~2 GB | Fast | Good |
| `medium` | ~4 GB | Moderate | Better |
| `large-v3-turbo` | ~6 GB | Fast | Near-best (default) |
| `large-v3` | ~8 GB | Slower | Best |

### Enabling speaker diarization

Speaker diarization requires a free HuggingFace access token and model approval:

1. Create a token at [huggingface.co/settings/tokens](https://huggingface.co/settings/tokens)
2. Accept the terms at [pyannote/speaker-diarization-3.1](https://huggingface.co/pyannote/speaker-diarization-3.1)
3. Accept the terms at [pyannote/segmentation-3.0](https://huggingface.co/pyannote/segmentation-3.0)
4. Set the token in your environment:

```bash
$ export HF_TOKEN="YOUR_HUGGINGFACE_TOKEN"
```

Then enable diarization in `config.yaml`:

```yaml
transcriber:
  backend: whisperx
  diarization:
    enabled: true
    hf_token_env: HF_TOKEN
```

---

## Customization

Three layers, in order of effort:

### Layer 1 — Prompt instructions (no code required)

Add free-form rules to `config.yaml` that the LLM follows when building the note:

```yaml
note:
  custom_prompt_instructions: |
    Write the summary as bullet points, not prose.
    Format people's full names as [[First Last]] wikilinks.
    Add an "Open Questions" section for anything unresolved.
```

### Layer 2 — Custom Jinja2 template

Set `note.template_file` to a `.j2` file to control note layout. Copy the built-in default from `note_writer.py` as a starting point. All extracted fields are available as template variables — see [`docs/customization.md`](docs/customization.md) for the full variable reference.

### Layer 3 — Modify `llm.py` directly

Add new extracted fields to the JSON schema in `build_system_prompt()`, add defaults in `_parse_llm_response()`, and expose them as template variables in `note_writer.render_and_write()`. See [`docs/customization.md`](docs/customization.md) for a step-by-step walkthrough.

---

## Running as a Service

### Auto-start at login (recommended)

```bash
$ python install.py --setup
```

This registers `tray.py` with Task Scheduler (Windows) or launchd (Mac). After the next login, the tray icon appears automatically — no terminal needed.

To remove it:

```bash
# Windows: open Task Scheduler, find "ObsidianAudioPipeline", delete it
# Mac:
$ launchctl unload ~/Library/LaunchAgents/com.obsidian-audio-pipeline.plist
```

### Manual — foreground (development)

```bash
$ python main.py
```

Logs go to stdout and to `pipeline.log` in the project folder.

### Manual — Task Scheduler (Windows, without install.py)

Create `run_pipeline.bat`:

```batch
@echo off
set ANTHROPIC_API_KEY=YOUR_ANTHROPIC_API_KEY
cd C:\PATH\TO\obsidian-audio-pipeline
C:\PATH\TO\venv\Scripts\python.exe tray.py
```

In Task Scheduler: Create Basic Task > Trigger: At log on > Action: Start a program > point to the `.bat` file.

### Manual — launchd (Mac, without install.py)

Create `~/Library/LaunchAgents/com.obsidian-audio-pipeline.plist` — see [`docs/building.md`](docs/building.md) for the full plist template.

---

## Project Structure

```
obsidian-audio-pipeline/
├── main.py             Entry point — loads config, starts watcher
├── config.py           Loads config.yaml, deep-merges with defaults
├── watcher.py          watchdog handler — detects new audio, waits for stability, calls pipeline
├── pipeline.py         Orchestrator — transcriber → llm → note_writer → cleanup
├── transcriber.py      Audio → plain-text transcript + duration
├── llm.py              Transcript → structured JSON via LLM (primary customization point)
├── note_writer.py      JSON + Jinja2 template → .md file written to vault
├── vault_tags.py       Scans vault .md files for unique tags (cached per session)
├── state.py            Persistent processed-file tracking; startup catch-up scan
├── tray.py             System tray process — owns main.py as subprocess, auto-restart
├── log_window.py       Live log tail viewer (tkinter)
├── settings_window.py  Tabbed config editor (tkinter)
├── install.py          GPU-aware installer + login service registration
├── config.yaml         User configuration (edit this)
├── requirements.txt    Python dependencies
├── templates/          Custom Jinja2 note templates
├── assets/             Tray icon images
├── tests/              pytest test suite
└── docs/               Architecture, building, customization, getting-started
```

---

## Contributing

The codebase follows a few hard conventions:

- **Independent pipeline stages** — `transcriber.py`, `llm.py`, `note_writer.py` do not import each other. Keep them that way.
- **Config flows downward** — modules receive the config dict as a parameter. Never import config globally.
- **New LLM backends** go in `llm.py` following the `_call_<backend>()` pattern.
- **New transcription backends** go in `transcriber.py` following the `_transcribe_<backend>()` pattern.
- **Note structure changes** live in exactly two files: `llm.py` (JSON schema) and `note_writer.py` (template).
- **Errors log and raise** — never silently swallow exceptions in pipeline stages.

Run the test suite:

```bash
$ pytest tests/
```

---

## Known Limitations

- **First-run model download** — `large-v3-turbo` downloads ~1.6 GB of weights on first use. Expect a 2–5 minute delay that looks like a hang; check `pipeline.log`.
- **LLM context limits** — recordings longer than ~60 minutes may exceed the model's context window. Consider a model with a larger context or add transcript chunking.
- **iCloud Drive** — FSEvents is unreliable for cloud-synced folders on Mac. Use a local watch folder and rely on iCloud sync to deliver files there.
- **Settings GUI strips YAML comments** — `settings_window.py` rewrites `config.yaml` via `yaml.dump`, which removes all comments. Hand-edit the file if you want to preserve them.
- **Windows paths with spaces** — Task Scheduler batch files need careful quoting around paths that contain spaces.
- **Diarization model download** — pyannote downloads additional weights (~500 MB) on first diarization run.
- **Python 3.11+ required** — the codebase uses `X | Y` union syntax not available in older Python releases.

---

## License

MIT — see `LICENSE` for details.

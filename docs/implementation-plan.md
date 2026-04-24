# Implementation Plan

Phased build plan. Check off tasks as they are completed.
Claude Code: update this file as work is done.

---

## Phase 1 — Core Pipeline (Foundation)

Get a single audio file → markdown note working end-to-end.

- [ ] Verify Python 3.11+ environment and venv setup
- [ ] Install dependencies via `python install.py` (auto-detects CUDA)
- [ ] Configure `config.yaml` with real paths (watch folder, vault folder)
- [ ] Set LLM env var (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, or run `ollama serve`)
- [ ] Run pipeline manually on a test audio file
- [ ] Verify note appears in Obsidian vault with correct frontmatter
- [ ] Verify vault tags are being scanned and injected into LLM prompt
- [ ] Confirm audio file is handled correctly per `on_complete.audio_file_action`

**Exit criteria:** Drop a real meeting recording → formatted `.md` appears in vault.

---

## Phase 2 — Watcher & Stability

Make the background service reliable.

- [ ] Start `main.py` and confirm watcher detects file drops
- [ ] Test stability polling with a large audio file
- [ ] Test multiple files dropped in quick succession
- [ ] Confirm duplicate-detection prevents double-processing
- [ ] Verify `pipeline.log` is written and readable
- [ ] Test graceful Ctrl+C shutdown
- [ ] Verify startup catch-up scan processes files dropped while offline

**Exit criteria:** Watcher runs for 24h without crashing; handles edge cases cleanly.

---

## Phase 3 — Note Quality Tuning

Dial in the LLM output to match your Obsidian workflow.

- [ ] Review first 5 real meeting notes — identify what's missing or wrong
- [ ] Tune `custom_prompt_instructions` in config.yaml based on review
- [ ] Verify `[[wikilinks]]` are generated correctly for project names and people
- [ ] Verify tags are being selected from vault vocabulary (not invented)
- [ ] Check to-do extraction — are real action items being captured?
- [ ] Check decision extraction — are decisions distinguished from action items?
- [ ] Tune Whisper model size if accuracy is poor on your accent/audio quality
- [ ] Enable and test speaker diarization (set `diarization.enabled: true`, configure HF_TOKEN)

**Exit criteria:** Notes are useful without manual editing for ~80% of recordings.

---

## Phase 4 — Custom Template

Replace the default template with one tuned to your vault structure.

- [ ] Decide on final note structure (sections, ordering, wikilink conventions)
- [x] Copy `DEFAULT_TEMPLATE` from `note_writer.py` to a `.j2` file
- [x] Set `note.template_file` in config.yaml to point at the new template
- [ ] Add any extra extracted fields needed (see customization.md Layer 3)
- [ ] Validate template with several different recording types (meeting, voice memo, lecture)
- [ ] Confirm `subfolder_pattern` puts notes in the right vault location

**Exit criteria:** Notes drop directly into your workflow with no reformatting needed.

---

## Phase 4 — Testing

Unit tests for note_writer and llm parsing. Run with `pytest tests/`.

- [x] `tests/test_note_writer.py` — _sanitize_filename edge cases
- [x] `tests/test_note_writer.py` — _format_duration all ranges
- [x] `tests/test_note_writer.py` — _build_context key presence and config passthrough
- [x] `tests/test_note_writer.py` — _load_template: null, valid path, missing path
- [x] `tests/test_note_writer.py` — render_and_write happy path, custom template, subfolder pattern
- [x] `tests/test_note_writer.py` — _resolve_output_path with and without subfolder_pattern
- [x] `tests/test_llm.py` — _parse_llm_response: valid JSON, code fences, think tags, prose prefix
- [x] `tests/test_llm.py` — _parse_llm_response: invalid JSON raises, missing fields get defaults
- [x] `tests/test_llm.py` — _parse_llm_response: tag stripping, empty todo dropped
- [x] `tests/test_llm.py` — build_system_prompt: vault tags included, custom instructions included

---

## Phase 5 — Launcher, Tray App & One-Command Installer

Replace manual service setup with a polished user-facing shell.
Full implementation plan: `.claude/plans/launcher-tray-and-installer-phase.md`

- [x] Icon assets — `assets/icon.png` and `assets/icon_active.png`
- [x] `log_window.py` — live log tail viewer (tkinter)
- [x] `settings_window.py` — tabbed form-based config editor (tkinter)
  - [x] Tab 1: Folders (watch, vault, archive, on-complete action)
  - [x] Tab 2: Transcription (backend, model, diarization sub-section)
  - [x] Tab 3: AI / LLM (backend, model, test-connection button)
  - [x] Tab 4: Note Format (template, transcript, tags, custom instructions)
- [x] `tray.py` — persistent tray process owning main.py as subprocess
  - [x] Mac: rumps menu bar implementation
  - [x] Windows: pystray system tray implementation
  - [x] Subprocess health monitoring + auto-restart
  - [x] Status polling from pipeline.log
- [x] `install.py` — extend with first-run wizard + OS service registration
  - [x] Mac: write and load launchd plist
  - [x] Windows: register Task Scheduler job via schtasks
- [x] `docs/getting-started.md` — GitHub Getting Started page with Python install guide

**Exit criteria:** Record on phone → note in Obsidian with no terminal interaction required.

---

## Phase 6 — Enhancements (Backlog)

Nice-to-haves, implement when Phase 1–5 are solid.

- [ ] **Model lifecycle management** — `transcriber.unload_after_use: true` to free VRAM between jobs
- [ ] **Configurable watcher poll interval** — expose `watcher.poll_interval_seconds` in config.yaml
- [ ] **Confidence flagging** — mark low-confidence Whisper segments with `[?]` in transcript
- [ ] **Retry logic** — automatic retry with backoff on transient API failures
- [ ] **Notification** — macOS/Windows toast when a note is written
- [ ] **Tag refresh** — force vault tag rescan via tray menu item
- [ ] **Multi-vault support** — route notes to different vault folders by filename pattern
- [ ] **Template selection** — choose template per audio source (meeting vs. memo vs. lecture)
- [ ] **Obsidian URI integration** — open the new note in Obsidian automatically after writing
- [ ] **State file pruning** — optional max-age or max-entries cap on `pipeline_state.json`

---

## Phase 7 — Open-Source Packaging

Make the project installable and distributable.

- [ ] `config.example.yaml` — placeholder-path copy of config.yaml for sharing
- [ ] `.env.example` — placeholder API key vars
- [ ] `LICENSE` — MIT recommended
- [ ] `README.md` — quick-start, config reference, screenshot of a generated note
- [ ] `CONTRIBUTING.md` — how to add new LLM backend, transcriber backend, template
- [ ] `pyproject.toml` — project metadata, dependencies, `obsidian-audio-pipeline` CLI entry point
- [ ] GitHub Actions CI — lint (ruff), type-check (mypy), dry-run integration test
- [ ] PyPI publish
- [ ] PyInstaller binary release (zero-Python-install option)

**Exit criteria:** `pip install obsidian-audio-pipeline` → edit one config file → works.

---

## Completed Work (this session)

- [x] WhisperX backend in `transcriber.py` — word alignment + pyannote 3.1 diarization
- [x] `state.py` — persistent processed-file tracking; startup catch-up scan in `watcher.py`
- [x] `install.py` — GPU-aware installer (detects NVIDIA, installs correct torch wheel)
- [x] LLM Ollama backend hardened — `format: json`, `temperature: 0`, `<think>` tag stripping
- [x] `config.yaml` updated — whisperx backend, large-v3-turbo, qwen3:32b, full diarization block
- [x] `config.py` updated — whisperx in valid backends, expanded transcriber defaults
- [x] `docs/building.md` updated — install step now uses `install.py`
- [x] `tray.py` — pystray (Windows) + rumps (Mac), subprocess health-check, auto-restart (3x), log/settings window launch
- [x] `install.py` extended — `--setup` flag for Task Scheduler (Windows) / launchd (Mac) service registration
- [x] `assets/generate_icons.py` + generated `assets/icon.png` and `assets/icon_active.png` (Pillow, geometric mic shape)
- [x] `docs/getting-started.md` — non-technical user guide covering install through startup registration
- [x] `requirements.txt` — added pystray, rumps (macOS-only marker), Pillow
- [x] `.gitignore` updated — excludes `.claude/` and `pipeline_state.json`

---

## Known Issues / Watch Items

- `whisperx` first run downloads large-v3-turbo weights (~1.5 GB) and wav2vec2 alignment
  model — expect a 2-5 minute delay on first use
- Very long recordings (60+ min) may hit LLM context limits — may need transcript chunking
- iCloud Drive requires polling observer; FSEvents not reliable for cloud-synced folders
- `yaml.dump` in settings_window.py (Phase 5) will strip YAML comments — known limitation;
  future option: switch to `ruamel.yaml`
- Windows paths with spaces need careful quoting in the Task Scheduler batch file

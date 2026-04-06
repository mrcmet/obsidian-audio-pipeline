# Implementation Plan

Phased build plan. Check off tasks as they are completed.
Claude Code: update this file as work is done.

---

## Phase 1 — Core Pipeline (Foundation)

Get a single audio file → markdown note working end-to-end.

- [ ] Verify Python 3.11+ environment and venv setup
- [ ] Install and smoke-test `faster-whisper` (transcribe a short test file)
- [ ] Install and smoke-test `anthropic` SDK (simple API call)
- [ ] Configure `config.yaml` with real paths (watch folder, vault folder)
- [ ] Set `ANTHROPIC_API_KEY` environment variable
- [ ] Run `pipeline.py` manually on a test audio file (single-file test, no watcher)
- [ ] Verify note appears in Obsidian vault with correct frontmatter
- [ ] Verify vault tags are being scanned and injected into LLM prompt
- [ ] Confirm audio file is archived after successful run

**Exit criteria:** Drop a real meeting recording → formatted `.md` appears in vault.

---

## Phase 2 — Watcher & Stability

Make the background service reliable.

- [ ] Start `main.py` and confirm watcher detects file drops
- [ ] Test with large audio file (verify stability polling works — file fully written before processing)
- [ ] Test with multiple files dropped in quick succession
- [ ] Confirm duplicate-detection prevents double-processing
- [ ] Verify `pipeline.log` is written and readable
- [ ] Test graceful Ctrl+C shutdown

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
  - Start with `base`, try `small` if proper nouns are being mangled
- [ ] Consider speaker diarization if meetings have multiple speakers
  (requires switching transcriber to AssemblyAI or Deepgram — see customization.md)

**Exit criteria:** Notes are useful without manual editing for ~80% of recordings.

---

## Phase 4 — Custom Template

Replace the default template with one tuned to your vault structure.

- [ ] Decide on final note structure (sections, ordering, wikilink conventions)
- [ ] Copy `DEFAULT_TEMPLATE` from `note_writer.py` to `docs/my-template.md.j2`
- [ ] Set `note.template_file` in config.yaml to point at the new template
- [ ] Add any extra extracted fields needed (see customization.md Layer 3)
- [ ] Validate template with several different recording types (meeting, voice memo, lecture)
- [ ] Confirm `subfolder_pattern` puts notes in the right vault location

**Exit criteria:** Notes drop directly into your workflow with no reformatting needed.

---

## Phase 5 — Background Service

Set up auto-start so the pipeline runs without manual intervention.

- [ ] **Mac:** Create and load launchd `.plist` (see docs/building.md)
  - [ ] Verify it survives a reboot
  - [ ] Verify it restarts after a crash (KeepAlive = true)
  - [ ] Confirm env vars are available to the service process
- [ ] **Windows:** Create Task Scheduler job (see docs/building.md)
  - [ ] Test that it starts at login
  - [ ] Verify the batch file sets env vars correctly
- [ ] Set up mobile audio capture feeding the watch folder
  - Option A: iCloud Drive shared folder (Mac + iPhone)
  - Option B: OneDrive (cross-platform)
  - Option C: Dropbox
- [ ] Test end-to-end mobile → vault workflow

**Exit criteria:** Record on phone → note in Obsidian with no manual steps.

---

## Phase 6 — Enhancements (Backlog)

Nice-to-haves, implement when Phase 1–5 are solid.

- [ ] **Model lifecycle management** — optional config flag (`transcriber.unload_after_use: true`) to release the Whisper model from RAM between jobs; optional Ollama start/stop via `ollama serve` subprocess so the server only runs during processing
- [ ] **Configurable watcher poll interval** — expose `watcher.poll_interval_seconds` in `config.yaml` (default 5); applies when polling observer is active (iCloud/network paths); allow values down to 1 s for near-real-time response
- [ ] **Speaker diarization** — integrate AssemblyAI or Deepgram for "Speaker 1 / Speaker 2" labels
- [ ] **Confidence flagging** — mark low-confidence Whisper segments with `[?]` in transcript
- [ ] **Retry logic** — automatic retry with backoff on transient API failures
- [ ] **Notification** — macOS/Windows toast notification when a note is written
- [ ] **Web UI** — simple Flask/FastAPI status dashboard showing recent pipeline runs
- [ ] **Tag refresh command** — slash command or menu option to force vault tag rescan
- [ ] **Multi-vault support** — route notes to different vault folders based on audio filename pattern
- [ ] **Template selection** — choose template per audio source (meeting vs. personal memo vs. lecture)
- [ ] **Obsidian URI integration** — open the new note in Obsidian automatically after writing

---

## Phase 7 — Open-Source Packaging

Make the project installable and distributable as a proper OSS tool.

- [ ] Add `pyproject.toml` with project metadata, dependencies, and a `obsidian-audio-pipeline` CLI entry point
- [ ] Add `LICENSE` file (MIT recommended for broad adoption)
- [ ] Add `README.md` — quick-start, config reference, screenshot of a generated note
- [ ] Add `.gitignore` (venv, `*.pyc`, `pipeline.log`, `config.yaml` with real paths)
- [ ] Add `.env.example` with placeholder API key vars (never commit the real `.env`)
- [ ] Ship a `config.example.yaml` (the current `config.yaml` with placeholder paths) so `config.yaml` can be gitignored
- [ ] Write a `CONTRIBUTING.md` — how to add a new LLM backend, new transcriber backend, new template
- [ ] Publish to PyPI so users can `pip install obsidian-audio-pipeline`
- [ ] Add a GitHub Actions CI workflow — lint (ruff), type-check (mypy), and a dry-run integration test with a short fixture audio clip
- [ ] Create a GitHub release with pre-built binary via PyInstaller (zero-Python-install option for non-developers)

**Exit criteria:** `pip install obsidian-audio-pipeline` → edit one config file → `obsidian-audio-pipeline` command works.

---

## Known Issues / Watch Items

- `faster-whisper` first run downloads model weights (~150 MB for `base`) — expect delay
- Very long recordings (60+ min) may hit LLM context limits — may need transcript chunking
- iCloud Drive requires polling observer (`watcher.poll_interval_seconds` in config); FSEvents not reliable for cloud-synced folders
- Windows file paths with spaces need quoting in the `.bat` file

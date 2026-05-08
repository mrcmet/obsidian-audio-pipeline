# TypeScript / Obsidian Plugin Migration Assessment

High-level feasibility notes for porting this project to TypeScript as an Obsidian plugin.
Not a full migration plan — just major blockers and missing ecosystem equivalents.

---

## Major Blockers

### 1. faster-whisper — local transcription (Hard)

No NPM equivalent exists for local Whisper inference via CTranslate2.
Options if local transcription is required:

- Keep Python as a sidecar process alongside the plugin (complex to distribute)
- Build native bindings to `whisper.cpp` (significant project on its own)
- Drop local transcription entirely and use the OpenAI Whisper API only

This is the single biggest blocker for a pure TypeScript port.

### 2. Obsidian plugin sandbox (Medium-High)

Obsidian plugins run in a sandboxed renderer process. Constraints:

- No arbitrary filesystem access outside the vault
- No subprocess / shell calls (rules out local Whisper unless via a companion app)
- File watching must use Obsidian's vault event API, not `chokidar` or `watchdog`
- All file I/O must go through `vault.adapter`

This means the "watch an arbitrary folder on disk" model changes fundamentally —
the drop folder would need to be inside the vault, or require a separate companion app.

### 3. Jinja2 templates (Medium)

No perfect TypeScript equivalent. `nunjucks` is the closest but syntax and available
filters differ. The default template and any custom `.j2` files would need rewriting.

---

## Medium Concerns

| Python | TypeScript equivalent | Notes |
|---|---|---|
| `watchdog` | Obsidian vault events API | Different model entirely — see blocker #2 |
| `python-frontmatter` | `gray-matter` | Fine |
| `pyyaml` | `js-yaml` | Fine |
| `anthropic` SDK | `@anthropic-ai/sdk` | Official; fine |
| `openai` SDK | `openai` npm package | Official; fine |
| `datetime` / `strftime` | `date-fns` or `dayjs` | Fine |
| `shutil.move` | `fs.rename` | Fine |

---

## What Transfers Cleanly

- Config injection pattern (all modules receive config as parameter — no globals)
- LLM response parsing logic and resilience (JSON extraction, fallback defaults)
- Note data schema and validation
- Vault tag scanning logic (`rglob` → recursive `vault.adapter` walk)
- Archive / delete / leave file handling logic
- All three LLM backends (Anthropic, OpenAI, Ollama) have good NPM equivalents

---

## Bottom Line

**If cloud-only transcription is acceptable:** moderate-effort port. The core logic is
clean and portable; the main rewrite cost is adapting to the Obsidian plugin API model
and replacing Jinja2.

**If local transcription must be preserved:** requires a companion native app or Python
helper process running alongside the plugin, which significantly complicates packaging
and the user setup story.

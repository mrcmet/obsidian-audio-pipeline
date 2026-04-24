# Getting Started

## What this does

Obsidian Audio Pipeline watches a folder on your computer for audio files (voice memos,
meeting recordings, any `.m4a`/`.mp3`/`.wav`). When a file lands there it automatically
transcribes the audio, sends the transcript to an AI, and writes a formatted Obsidian
note — with a summary, action items, decisions, and a full transcript — directly into
your vault.

---

## Requirements

- **Python 3.11 or newer** — check with `python --version` in a terminal.
  Download from [python.org](https://www.python.org/downloads/) if needed.
- **An AI API key** — one of:
  - [Anthropic](https://console.anthropic.com/) (`ANTHROPIC_API_KEY`) — recommended
  - [OpenAI](https://platform.openai.com/) (`OPENAI_API_KEY`)
  - [Ollama](https://ollama.com/) running locally — no key needed
- **Disk space** — the Whisper transcription model downloads automatically on first run:
  - `tiny` / `base`: ~150–300 MB
  - `small`: ~500 MB
  - `large-v3-turbo` (default): ~1.6 GB

---

## Installation

### 1. Download the project

Download and unzip, or clone with git:

```
git clone https://github.com/your-username/obsidian-audio-pipeline.git
```

Open a terminal and navigate into the folder:

```
cd obsidian-audio-pipeline
```

### 2. Create a Python virtual environment

```
python -m venv venv
```

Activate it:

- **Mac / Linux:** `source venv/bin/activate`
- **Windows:** `venv\Scripts\activate`

You should see `(venv)` at the start of your terminal prompt.

### 3. Install dependencies

```
python install.py
```

This auto-detects your GPU and installs the right version of PyTorch. It takes a few
minutes on first run.

If you hit an error about CUDA, force CPU mode:

```
python install.py --cpu
```

### 4. Set your API key

**Mac / Linux** — paste this into your terminal (replace with your actual key):

```
export ANTHROPIC_API_KEY="sk-ant-..."
```

**Windows PowerShell:**

```
$env:ANTHROPIC_API_KEY = "sk-ant-..."
```

To make this permanent, add it to your shell profile (`.zshrc`, `.bashrc`) or Windows
Environment Variables in System Settings.

If you are using Ollama instead of Anthropic, skip this step — Ollama runs locally and
needs no key.

---

## Configuration

Open `config.yaml` in any text editor. You must change two lines:

```yaml
watch_folder: ~/Desktop/AudioDrop
obsidian_vault_folder: ~/Documents/Obsidian/Inbox
```

- **`watch_folder`** — create this folder anywhere you like. Drop audio files here.
- **`obsidian_vault_folder`** — the folder inside your vault where notes will be written.
  This folder must already exist in Obsidian.

### LLM backend choice

The default is Anthropic Claude. To use a different AI:

**OpenAI:**
```yaml
llm:
  backend: openai
  model: gpt-4o
```

**Ollama (local, no API key):**
```yaml
llm:
  backend: ollama
  model: llama3
```

Everything else in `config.yaml` has sensible defaults. You can leave it as-is until you
want to tune the note format.

---

## Running

Start the tray app:

```
python tray.py
```

A small icon appears in your system tray (Windows) or menu bar (Mac). The pipeline starts
automatically in the background.

To process a recording:

1. Drop any audio file (`.m4a`, `.mp3`, `.wav`, `.ogg`, `.flac`) into your `watch_folder`.
2. Wait 10–60 seconds depending on the length of the recording.
3. The note appears in your Obsidian vault folder.

The tray menu gives you:

- **Open Log** — live view of what the pipeline is doing
- **Settings** — edit config without touching `config.yaml` directly
- **Stop / Start / Restart** — control the pipeline
- **Quit** — stop everything and close the tray app

---

## Run at startup

To have the tray app launch automatically when you log in:

```
python install.py --setup
```

This registers `tray.py` with Task Scheduler (Windows) or launchd (Mac). After the next
login the tray icon will appear automatically without opening a terminal.

To remove it later:

- **Windows:** open Task Scheduler, find "ObsidianAudioPipeline", and delete it.
- **Mac:** `launchctl unload ~/Library/LaunchAgents/com.obsidian-audio-pipeline.plist`

---

## Troubleshooting

### Check the log

Open the tray menu and click **Open Log**, or open `pipeline.log` in the project folder
with any text editor. Every step of the pipeline is logged there with timestamps.

### "API key not set" or authentication error

The API key environment variable is not visible to the pipeline. Set it in your shell
profile (permanent), or for a quick test:

**Mac / Linux:**
```
ANTHROPIC_API_KEY="sk-ant-..." python tray.py
```

**Windows PowerShell:**
```
$env:ANTHROPIC_API_KEY = "sk-ant-..."; python tray.py
```

### Whisper model downloads on first run

The first time a recording is processed, Whisper downloads its model weights. This can
take several minutes and looks like it is hanging — it is not. Check `pipeline.log` for
download progress.

### Wrong vault path — note not appearing

Verify the path in `config.yaml` points to a folder that actually exists inside Obsidian.
The folder must exist; the pipeline does not create it.

Test the path from a terminal:

```
python -c "from vault_tags import get_vault_tags; print(get_vault_tags('~/Documents/Obsidian'))"
```

If that prints `[]` or an error, the vault path is wrong.

### File processed but note looks wrong

Open `pipeline.log` and look for `raw_llm_response`. That is exactly what the AI returned.
If the JSON looks malformed, the LLM may be hitting a context-length limit on a very long
recording. Try a shorter clip to confirm, then consider switching to a larger model.

### Tray icon does not appear (Windows)

Confirm `pystray` and `Pillow` are installed in the active virtualenv:

```
pip show pystray Pillow
```

If either is missing: `pip install pystray Pillow`.

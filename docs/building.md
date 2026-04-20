# Building & Running

## Requirements

- Python 3.11+
- An Anthropic API key (or OpenAI key if using that backend)
- For local transcription: a machine with enough RAM for the Whisper model
  - `tiny` / `base`: ~1 GB RAM, works fine on any modern laptop
  - `small`: ~2 GB RAM
  - `medium` / `large`: 4–8 GB RAM, significantly better accuracy

## Installation

```bash
# 1. Clone / copy the project folder
cd obsidian-audio-pipeline

# 2. Create virtual environment
python -m venv venv

# 3. Activate it
source venv/bin/activate        # Mac / Linux
# venv\Scripts\activate         # Windows

# 4. Install dependencies (use install.py — NOT pip install -r requirements.txt directly)
#    install.py auto-detects NVIDIA and installs the correct PyTorch variant first.
python install.py

# Override flags if needed:
#   python install.py --cuda    # force CUDA install (skip GPU detection)
#   python install.py --cpu     # force CPU-only (e.g. for CI or non-GPU machines)

# 5. Set API key (only needed for anthropic/openai LLM backends)
export ANTHROPIC_API_KEY="sk-ant-..."     # Mac/Linux
# $env:ANTHROPIC_API_KEY = "sk-ant-..."  # Windows PowerShell
```

> **Why `install.py` instead of `pip install -r requirements.txt`?**
> PyTorch ships separate wheels for CUDA and CPU. The CUDA wheel must be fetched
> from a custom index URL (`https://download.pytorch.org/whl/cu128`). `install.py`
> detects NVIDIA via `nvidia-smi`, installs the right torch variant first, then
> runs `requirements.txt` for everything else.

## Configuration

Edit `config.yaml`. Minimum required changes:

```yaml
watch_folder: ~/Desktop/AudioDrop          # Create this folder
obsidian_vault_folder: ~/Documents/Obsidian/Inbox   # Must exist in your vault
```

Everything else has sensible defaults.

## Running

```bash
# Foreground (development)
python main.py

# The watcher logs to stdout and to pipeline.log
# Drop an audio file into watch_folder and watch the output
```

## Testing Individual Stages

```bash
# Test transcription only
python - <<'EOF'
from transcriber import transcribe
from config import load_config
from pathlib import Path
transcript, duration = transcribe(Path("your-file.m4a"), load_config()["transcriber"])
print(f"Duration: {duration}s")
print(transcript[:500])
EOF

# Test LLM extraction (provide a transcript string)
python - <<'EOF'
from llm import extract_note_data
from config import load_config
from pathlib import Path
config = load_config()
data = extract_note_data("We discussed the Q3 roadmap. Mike will send the spec by Friday.", 
                         120.0, Path("test.m4a"), config)
import json; print(json.dumps(data, indent=2, default=str))
EOF

# Test vault tag scanning
python - <<'EOF'
from vault_tags import get_vault_tags
tags = get_vault_tags("~/Documents/Obsidian")
print(f"Found {len(tags)} tags:")
print(tags)
EOF

# Run full pipeline on a single file (no watcher)
python - <<'EOF'
from pipeline import run_pipeline
from config import load_config
from pathlib import Path
run_pipeline(Path("your-file.m4a"), load_config())
EOF
```

## Running as a Background Service

### Mac (launchd) — auto-starts at login

Create `~/Library/LaunchAgents/com.obsidian-audio-pipeline.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
    "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.obsidian-audio-pipeline</string>
    <key>ProgramArguments</key>
    <array>
        <string>/FULL/PATH/TO/venv/bin/python</string>
        <string>/FULL/PATH/TO/obsidian-audio-pipeline/main.py</string>
    </array>
    <key>WorkingDirectory</key>
    <string>/FULL/PATH/TO/obsidian-audio-pipeline</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/tmp/obsidian-audio-pipeline.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/obsidian-audio-pipeline.err</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>ANTHROPIC_API_KEY</key>
        <string>sk-ant-YOUR-KEY-HERE</string>
    </dict>
</dict>
</plist>
```

```bash
# Load it
launchctl load ~/Library/LaunchAgents/com.obsidian-audio-pipeline.plist

# Stop it
launchctl unload ~/Library/LaunchAgents/com.obsidian-audio-pipeline.plist

# Check status
launchctl list | grep obsidian
```

### Windows — Task Scheduler

Create `run_pipeline.bat`:
```batch
@echo off
set ANTHROPIC_API_KEY=sk-ant-YOUR-KEY-HERE
cd C:\path\to\obsidian-audio-pipeline
C:\path\to\venv\Scripts\python.exe main.py
```

In Task Scheduler: Create Basic Task → Trigger: At log on → Action: Start a program → point to `run_pipeline.bat`.

## Debugging

- Check `pipeline.log` in the project folder for timestamped output from every run
- Set `logging.basicConfig(level=logging.DEBUG)` in `main.py` for verbose output
- The `raw_llm_response` field in `note_data` holds the exact JSON the LLM returned — useful if note structure looks wrong
- If vault tags aren't loading, run the vault tag test snippet above to verify the path

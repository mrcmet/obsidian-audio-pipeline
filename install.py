#!/usr/bin/env python3
"""
install.py — Smart installer for obsidian-audio-pipeline.

Detects NVIDIA GPU via nvidia-smi and installs the CUDA-enabled PyTorch wheel
before installing the rest of requirements.txt. Running plain
'pip install -r requirements.txt' skips torch, so always use this script.

Usage:
    python install.py           # auto-detect GPU
    python install.py --cpu     # force CPU-only torch (e.g. for testing)
    python install.py --cuda    # force CUDA torch (skip detection)
    python install.py --setup   # register tray.py as a login-time auto-start service
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

# CUDA 12.8 wheel index — works for Ada Lovelace (RTX 4000/6000), Ampere,
# and all recent NVIDIA consumer/workstation GPUs.
_TORCH_INDEX_CUDA = "https://download.pytorch.org/whl/cu128"

_BASE_DIR = Path(__file__).parent.resolve()
_TRAY_PY = _BASE_DIR / "tray.py"


def _run(cmd: list[str]) -> None:
    print(f"\n  {' '.join(cmd)}\n")
    result = subprocess.run(cmd)
    if result.returncode != 0:
        sys.exit(result.returncode)


def _has_nvidia() -> bool:
    try:
        r = subprocess.run(
            ["nvidia-smi"],
            capture_output=True,
            timeout=10,
        )
        return r.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _setup_windows() -> None:
    python_exe = sys.executable
    tray_path = str(_TRAY_PY)
    cmd = [
        "schtasks", "/Create",
        "/TN", "ObsidianAudioPipeline",
        "/TR", f'"{python_exe}" "{tray_path}"',
        "/SC", "ONLOGON",
        "/F",
    ]
    print(f"Registering Task Scheduler job: ObsidianAudioPipeline")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        print("Success. The tray app will start automatically at next login.")
        print("To start it now: python tray.py")
    else:
        print(f"schtasks failed (exit {result.returncode}):")
        print(result.stdout.strip())
        print(result.stderr.strip())
        sys.exit(result.returncode)


def _setup_mac() -> None:
    import plistlib

    python_exe = sys.executable
    tray_path = str(_TRAY_PY)
    label = "com.obsidian-audio-pipeline"
    plist_path = Path.home() / "Library" / "LaunchAgents" / f"{label}.plist"
    plist_path.parent.mkdir(parents=True, exist_ok=True)

    plist_data = {
        "Label": label,
        "ProgramArguments": [python_exe, tray_path],
        "WorkingDirectory": str(_BASE_DIR),
        "RunAtLoad": True,
        "KeepAlive": True,
        "StandardOutPath": "/tmp/obsidian-audio-pipeline.log",
        "StandardErrorPath": "/tmp/obsidian-audio-pipeline.err",
    }

    with open(plist_path, "wb") as fh:
        plistlib.dump(plist_data, fh)
    print(f"Wrote launchd plist: {plist_path}")

    result = subprocess.run(["launchctl", "load", str(plist_path)], capture_output=True, text=True)
    if result.returncode == 0:
        print("Success. The tray app will start automatically at next login.")
        print("To start it now: python tray.py")
    else:
        print(f"launchctl load failed (exit {result.returncode}):")
        print(result.stdout.strip())
        print(result.stderr.strip())
        sys.exit(result.returncode)


def _setup_service() -> None:
    print("Obsidian Audio Pipeline — Service Registration")
    print("=" * 48)
    if sys.platform == "win32":
        _setup_windows()
    elif sys.platform == "darwin":
        _setup_mac()
    else:
        print("Auto-start registration is only supported on Windows and macOS.")
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="Install obsidian-audio-pipeline dependencies.")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--cpu", action="store_true", help="Force CPU-only PyTorch.")
    group.add_argument("--cuda", action="store_true", help="Force CUDA PyTorch (skip GPU detection).")
    parser.add_argument(
        "--setup",
        action="store_true",
        help="Register tray.py as a login-time auto-start service (skips pip install).",
    )
    args = parser.parse_args()

    if args.setup:
        _setup_service()
        return

    print("Obsidian Audio Pipeline — Installer")
    print("=" * 42)

    if args.cpu:
        use_cuda = False
        print("Mode: CPU-only (--cpu flag set)")
    elif args.cuda:
        use_cuda = True
        print("Mode: CUDA (--cuda flag set)")
    else:
        use_cuda = _has_nvidia()
        if use_cuda:
            print("NVIDIA GPU detected — installing PyTorch with CUDA 12.8 support.")
        else:
            print("No NVIDIA GPU detected — installing CPU-only PyTorch.")

    # Step 1: install torch with the correct variant.
    if use_cuda:
        _run([
            sys.executable, "-m", "pip", "install",
            "torch",
            "--index-url", _TORCH_INDEX_CUDA,
        ])
    else:
        _run([sys.executable, "-m", "pip", "install", "torch"])

    # Step 2: install everything else.
    print("Installing remaining dependencies from requirements.txt ...")
    _run([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])

    print("\nInstallation complete.")
    print("Next: edit config.yaml with your paths, then run: python tray.py")


if __name__ == "__main__":
    main()

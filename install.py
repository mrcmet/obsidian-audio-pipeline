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
"""

from __future__ import annotations

import argparse
import subprocess
import sys

# CUDA 12.8 wheel index — works for Ada Lovelace (RTX 4000/6000), Ampere,
# and all recent NVIDIA consumer/workstation GPUs.
_TORCH_INDEX_CUDA = "https://download.pytorch.org/whl/cu128"


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


def main() -> None:
    parser = argparse.ArgumentParser(description="Install obsidian-audio-pipeline dependencies.")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--cpu", action="store_true", help="Force CPU-only PyTorch.")
    group.add_argument("--cuda", action="store_true", help="Force CUDA PyTorch (skip GPU detection).")
    args = parser.parse_args()

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
    print("Next: edit config.yaml with your paths, then run: python main.py")


if __name__ == "__main__":
    main()

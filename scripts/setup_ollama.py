#!/usr/bin/env python3
"""
Cross-platform wrapper for Ollama model setup on Windows.

Usage:
    python scripts/setup_ollama.py
    python scripts/setup_ollama.py --force
    python scripts/setup_ollama.py --skip-download
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description="Deploy Ollama vision model for CUA-Skill Agent")
    parser.add_argument("--model-name", default=None, help="Override model name (default: read from config)")
    parser.add_argument("--force", action="store_true", help="Re-download and recreate model")
    parser.add_argument("--skip-download", action="store_true", help="Use existing GGUF files in scripts/models/")
    parser.add_argument("--skip-test", action="store_true", help="Skip vision API smoke test")
    args = parser.parse_args()

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ps1 = os.path.join(root, "scripts", "setup_ollama.ps1")

    if sys.platform != "win32":
        print("This project targets Windows. On Linux/macOS, install Ollama manually:")
        print("  https://ollama.com/download")
        print("Then create the vision model using scripts/Modelfile.qwen2.5vl-vision")
        print("and GGUF files from https://huggingface.co/chatpig/qwen2.5-vl-7b-it-gguf")
        return 1

    if not os.path.isfile(ps1):
        print(f"Missing script: {ps1}")
        return 1

    cmd = [
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        ps1,
    ]
    if args.model_name:
        cmd += ["-ModelName", args.model_name]
    if args.force:
        cmd.append("-Force")
    if args.skip_download:
        cmd.append("-SkipDownload")
    if args.skip_test:
        cmd.append("-SkipTest")

    # Show resolved config model name for clarity
    cfg_path = os.path.join(root, "agent", "config_ollama.json")
    if os.path.isfile(cfg_path):
        with open(cfg_path, encoding="utf-8") as f:
            cfg = json.load(f)
        model = cfg.get("planner", {}).get("expertises", {}).get("ollama", {}).get("model_name")
        if model:
            print(f"[info] config model_name: {model}")

    print("[info] running:", " ".join(cmd))
    return subprocess.call(cmd)


if __name__ == "__main__":
    raise SystemExit(main())

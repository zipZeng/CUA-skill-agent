#!/usr/bin/env python3
"""
Full deployment for CUA-Skill Agent on Windows (Python deps + Ollama model).

Usage:
    python scripts/setup_ollama.py
    python scripts/setup_ollama.py --force
    python scripts/setup_ollama.py --skip-model
    python scripts/setup_ollama.py --skip-python
    python scripts/setup_ollama.py --no-venv
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Deploy CUA-Skill Agent: Python dependencies + Ollama vision model"
    )
    parser.add_argument("--model-name", default=None, help="Override Ollama model name")
    parser.add_argument("--force", action="store_true", help="Reinstall deps and recreate model")
    parser.add_argument("--skip-download", action="store_true", help="Use existing GGUF in scripts/models/")
    parser.add_argument("--skip-python", action="store_true", help="Skip pip / venv setup")
    parser.add_argument("--skip-model", action="store_true", help="Skip Ollama model setup")
    parser.add_argument("--skip-ollama-install", action="store_true", help="Skip Ollama for Windows install")
    parser.add_argument("--skip-test", action="store_true", help="Skip Ollama vision API test")
    parser.add_argument("--skip-verify", action="store_true", help="Skip test_match.py")
    parser.add_argument("--no-venv", action="store_true", help="Install into current Python, not .venv")
    args = parser.parse_args()

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ps1 = os.path.join(root, "scripts", "setup_ollama.ps1")

    if sys.platform != "win32":
        print("This setup script targets Windows.")
        print("Manual steps:")
        print("  1. pip install -r agent/requirements.txt flask pywin32")
        print("  2. Install Ollama: https://ollama.com/download")
        print("  3. Create model from scripts/Modelfile.qwen2.5vl-vision")
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
    if args.skip_python:
        cmd.append("-SkipPython")
    if args.skip_model:
        cmd.append("-SkipModel")
    if args.skip_ollama_install:
        cmd.append("-SkipOllamaInstall")
    if args.skip_test:
        cmd.append("-SkipTest")
    if args.skip_verify:
        cmd.append("-SkipVerify")
    if args.no_venv:
        cmd.append("-NoVenv")

    cfg_path = os.path.join(root, "agent", "config_ollama.json")
    if os.path.isfile(cfg_path):
        with open(cfg_path, encoding="utf-8") as f:
            cfg = json.load(f)
        model = cfg.get("planner", {}).get("expertises", {}).get("ollama", {}).get("model_name")
        if model:
            print(f"[info] config model_name: {model}")

    print("[info] running:", " ".join(cmd))
    env = os.environ.copy()
    env["PYTHON_FOR_SETUP"] = sys.executable
    return subprocess.call(cmd, env=env)


if __name__ == "__main__":
    raise SystemExit(main())

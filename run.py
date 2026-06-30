"""
CUA Skill — Computer Use Agent entry point (Ollama local version).

Usage:
    python run.py "Open Notepad and type Hello World"
    python run.py "打开浏览器搜索天气"
    python run.py --task "Open Calculator and compute 123+456"
"""

import sys
import os
import argparse

# Ensure the cua_skill package is importable
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from agent.agent_rag import CUARAGAgent
from agent.utils import Misc


def main():
    parser = argparse.ArgumentParser(
        description="CUA Skill — Computer Use Agent (Ollama local version)"
    )
    parser.add_argument(
        "task",
        nargs="?",
        default=None,
        help="Natural language instruction for the agent (e.g. 'Open Notepad and type Hello')",
    )
    parser.add_argument(
        "--task", "-t",
        dest="task_opt",
        default=None,
        help="Natural language instruction (alternative form)",
    )
    parser.add_argument(
        "--config", "-c",
        default=os.path.join(PROJECT_ROOT, "agent", "config_ollama.json"),
        help="Path to agent config JSON (default: agent/config_ollama.json)",
    )
    parser.add_argument(
        "--log-dir",
        default=os.path.join(PROJECT_ROOT, "results", "cua_logs"),
        help="Directory for execution logs",
    )
    args = parser.parse_args()

    instruction = args.task or args.task_opt
    if not instruction:
        print("Please provide a task instruction.")
        print('Example: python run.py "Open Notepad and type Hello World"')
        sys.exit(1)

    print(f"[CUA Skill] Loading config from: {args.config}")
    if not os.path.exists(args.config):
        print(f"ERROR: Config file not found: {args.config}")
        sys.exit(1)

    config = Misc.file_to_namespace(args.config)
    print(f"[CUA Skill] Model: {config.planner.model_class}")
    print(f"[CUA Skill] Task: {instruction}")
    print("-" * 50)

    agent = CUARAGAgent(config=args.config)
    agent.proceed(
        instruction=instruction,
        example={},
        explicit_log_dir=args.log_dir,
    )
    print("[CUA Skill] Done.")


if __name__ == "__main__":
    main()

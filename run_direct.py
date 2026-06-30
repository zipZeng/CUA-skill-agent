"""
Fast direct execution — bypasses LLM entirely for common task patterns.
Usage:
  python run_direct.py "Open Word"
  python run_direct.py "search hello world"
  python run_direct.py "calc 123+456"
  python run_direct.py "notepad hello world"
"""

import sys
import os
import time
import pyautogui

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def open_app(app_name: str):
    """Open an application by pressing Win key, typing its name, pressing Enter."""
    print(f"[Direct] Opening: {app_name}")
    pyautogui.hotkey("win")
    time.sleep(0.5)
    pyautogui.write(app_name, interval=0.05)
    time.sleep(0.5)
    pyautogui.press("enter")
    print("[Direct] Done.")


def search_web(query: str):
    """Open browser search via Win key + typing query."""
    print(f"[Direct] Searching: {query}")
    pyautogui.hotkey("win")
    time.sleep(0.5)
    pyautogui.write(query, interval=0.05)
    time.sleep(0.5)
    pyautogui.press("enter")
    print("[Direct] Done.")


def open_notepad(text: str = None):
    """Open Notepad and optionally type text."""
    print("[Direct] Opening Notepad...")
    pyautogui.hotkey("win")
    time.sleep(0.5)
    pyautogui.write("notepad", interval=0.05)
    time.sleep(0.5)
    pyautogui.press("enter")
    time.sleep(1.0)
    if text:
        pyautogui.write(text, interval=0.05)
    print("[Direct] Done.")


def open_calc(expression: str = None):
    """Open Calculator and optionally type expression."""
    print("[Direct] Opening Calculator...")
    pyautogui.hotkey("win")
    time.sleep(0.5)
    pyautogui.write("calculator", interval=0.05)
    time.sleep(0.5)
    pyautogui.press("enter")
    if expression:
        time.sleep(1.0)
        pyautogui.write(expression, interval=0.05)
        pyautogui.press("enter")
    print("[Direct] Done.")


TASK_PATTERNS = [
    (r"^open\s+(.+)$", lambda m: open_app(m.group(1))),
    (r"^打开\s*(.+)$", lambda m: open_app(m.group(1))),
    (r"^launch\s+(.+)$", lambda m: open_app(m.group(1))),
    (r"^search\s+(.+)$", lambda m: search_web(m.group(1))),
    (r"^搜索\s*(.+)$", lambda m: search_web(m.group(1))),
    (r"^notepad\s*(.*)$", lambda m: open_notepad(m.group(1) or None)),
    (r"^记事本\s*(.*)$", lambda m: open_notepad(m.group(1) or None)),
    (r"^calc\s*(.*)$", lambda m: open_calc(m.group(1) or None)),
    (r"^计算器\s*(.*)$", lambda m: open_calc(m.group(1) or None)),
]


def main():
    if len(sys.argv) < 2:
        print("Usage: python run_direct.py <task>")
        print("Examples:")
        print("  python run_direct.py \"Open Word\"")
        print("  python run_direct.py \"search python tutorial\"")
        print("  python run_direct.py \"notepad hello world\"")
        print("  python run_direct.py \"calc 123+456\"")
        sys.exit(1)

    task = " ".join(sys.argv[1:])
    print(f"[Direct] Task: {task}")
    print("-" * 40)

    import re
    for pattern, handler in TASK_PATTERNS:
        m = re.match(pattern, task, re.IGNORECASE)
        if m:
            handler(m)
            return

    print(f"[Direct] No pattern matched. Try the full agent: python run.py -c agent/config_ollama.json \"{task}\"")


if __name__ == "__main__":
    main()

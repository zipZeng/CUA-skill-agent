"""
Quick diagnostic tests — runs each component in isolation.
Usage: python test_quick.py [1|2|3]
  1 = Ollama vision test (1 LLM call)
  2 = Screenshot + pyautogui test (no LLM)
  3 = Plan only (1 step, no execution)
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_ollama_vision():
    """Test 1: Verify Ollama can see and understand the desktop (1 call)."""
    print("[Test 1] Ollama vision — sending screenshot to qwen2.5vl-vision...")
    import pyautogui
    from agent.llms import Ollama
    from agent.utils import Misc
    import time

    config = Misc.file_to_namespace("agent/config_ollama.json")
    llm = Ollama(config)

    # Take screenshot, resize small for speed
    screenshot = pyautogui.screenshot()
    screenshot = screenshot.resize((640, 360))
    import io
    buf = io.BytesIO()
    screenshot.save(buf, format="JPEG", quality=50)
    img_bytes = buf.getvalue()

    t0 = time.time()
    msg = llm.create_text_image_message(
        "What is on this screen? Answer in 1 short sentence.", img_bytes
    )
    resp = llm.get_completion([msg])
    elapsed = time.time() - t0
    print(f"  Response: {resp}")
    print(f"  Time: {elapsed:.1f}s")
    print("  PASS: Ollama vision OK")


def test_pyautogui():
    """Test 2: Verify desktop control works (no LLM, instant)."""
    print("[Test 2] pyautogui — testing mouse/keyboard control...")
    import pyautogui
    size = pyautogui.size()
    print(f"  Screen size: {size}")
    pos = pyautogui.position()
    print(f"  Mouse position: {pos}")
    print("  Opening Start menu (Win key)...")
    pyautogui.press("win")
    import time
    time.sleep(1)
    print("  Closing Start menu (Escape)...")
    pyautogui.press("escape")
    print("  PASS: pyautogui OK")


def test_plan_only():
    """Test 3: Run planner for 1 step, show what it decides (no execution)."""
    print("[Test 3] Plan only — 1 planning step, no execution...")
    import pyautogui
    import io
    import time
    from agent.planner import RAGPlanner
    from agent.utils import Misc

    config = Misc.file_to_namespace("agent/config_ollama.json")
    planner = RAGPlanner(config)
    planner.set_instruction("Open Word")

    screenshot = pyautogui.screenshot()
    screenshot = screenshot.resize((640, 360))
    buf = io.BytesIO()
    screenshot.save(buf, format="JPEG", quality=50)
    img_bytes = buf.getvalue()

    t0 = time.time()
    print("  build_memory...")
    planner.build_memory(img_bytes)
    print(f"  memory: {planner.memory[-1][:100]}...")

    print("  get_next_step_queries...")
    queries = planner.get_next_step_queries(img_bytes)
    if queries:
        print(f"  queries: {queries[:2]}...")
    else:
        print("  queries: DONE (no more steps)")

    action_cls, desc, is_base = planner.retrieve_next_step(img_bytes)
    if action_cls:
        print(f"  action: {action_cls.__name__}, desc: {desc}, is_base: {is_base}")
        action = planner.config_next_step(action_cls, img_bytes, desc)
        print(f"  configured: {action}")
    elapsed = time.time() - t0
    print(f"  Time: {elapsed:.1f}s")
    print("  PASS: Planner OK")


if __name__ == "__main__":
    choice = sys.argv[1] if len(sys.argv) > 1 else "1"
    tests = {"1": test_ollama_vision, "2": test_pyautogui, "3": test_plan_only}
    if choice in tests:
        tests[choice]()
    else:
        for t in tests.values():
            t()
            print()

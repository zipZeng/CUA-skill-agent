"""
CUA-Skill Web Console — Flask backend.
Usage: python web/app.py
"""
import sys
import os
import io
import re
import time
import json
import uuid
import threading

# Ensure project root is on sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from flask import Flask, request, jsonify, render_template
from agent.agent_rag import CUARAGAgent

app = Flask(__name__)
app.config["JSON_AS_ASCII"] = False

CONFIG_PATH = os.path.join(PROJECT_ROOT, "agent", "config_ollama.json")
LOG_DIR = os.path.join(PROJECT_ROOT, "results", "web_logs")
os.makedirs(LOG_DIR, exist_ok=True)

tasks = {}  # task_id -> {status, logs, instruction, mode, created_at}


def _capture_execution(task_id, instruction, mode):
    """Run agent in background thread, capturing all output."""
    buf = io.StringIO()
    old_stdout, old_stderr = sys.stdout, sys.stderr
    sys.stdout = sys.stderr = buf

    try:
        tasks[task_id]["logs"].append(
            f"[{_time()}] 开始执行: {instruction} (模式: {mode})"
        )

        if mode == "direct":
            _execute_direct(task_id, instruction)
        else:
            _execute_agent(task_id, instruction)

        tasks[task_id]["status"] = "completed"
        tasks[task_id]["logs"].append(f"[{_time()}] 执行完成")
    except Exception as e:
        tasks[task_id]["status"] = "failed"
        tasks[task_id]["logs"].append(f"[{_time()}] 错误: {e}")
    finally:
        sys.stdout, sys.stderr = old_stdout, old_stderr
        captured = buf.getvalue()
        if captured.strip():
            for line in captured.strip().split("\n"):
                if line.strip():
                    tasks[task_id]["logs"].append(f"[{_time()}] {line.strip()}")


def _execute_agent(task_id, instruction):
    """Full agent mode: skill matching + template + UIA."""
    tasks[task_id]["logs"].append(f"[{_time()}] 匹配指令到技能...")
    agent = CUARAGAgent(config=CONFIG_PATH)
    agent.proceed(
        instruction=instruction,
        example={},
        explicit_log_dir=os.path.join(LOG_DIR, task_id),
    )


def _execute_direct(task_id, instruction):
    """Direct mode: Win+type+enter, bypasses LLM."""
    import pyautogui

    patterns = [
        (r"^(?:open|打开|launch|启动)\s*(.+)", _direct_open),
        (r"^(?:search|搜索)\s*(.+)", _direct_search),
        (r"^(?:notepad|记事本)\s*(.*)", _direct_notepad),
        (r"^(?:calc|计算器|calculator)\s*(.*)", _direct_calc),
    ]
    instr_lower = instruction.lower()
    for pattern, handler in patterns:
        m = re.match(pattern, instruction, re.IGNORECASE)
        if m:
            handler(task_id, m, pyautogui)
            return

    # Generic fallback: Win + type + Enter
    tasks[task_id]["logs"].append(f"[{_time()}] 直接模式: Win + 输入 + Enter")
    pyautogui.hotkey("win")
    time.sleep(0.5)
    pyautogui.write(instruction, interval=0.05)
    time.sleep(0.5)
    pyautogui.press("enter")


def _direct_open(task_id, match, pag):
    app = match.group(1).strip()
    tasks[task_id]["logs"].append(f"[{_time()}] 打开应用: {app}")
    pag.hotkey("win")
    time.sleep(0.5)
    pag.write(app, interval=0.05)
    time.sleep(0.5)
    pag.press("enter")


def _direct_search(task_id, match, pag):
    query = match.group(1).strip()
    tasks[task_id]["logs"].append(f"[{_time()}] 搜索: {query}")
    pag.hotkey("win")
    time.sleep(0.5)
    pag.write(query, interval=0.05)
    time.sleep(0.5)
    pag.press("enter")


def _direct_notepad(task_id, match, pag):
    text = match.group(1).strip()
    tasks[task_id]["logs"].append(f"[{_time()}] 打开记事本")
    pag.hotkey("win")
    time.sleep(0.5)
    pag.write("notepad", interval=0.05)
    time.sleep(0.5)
    pag.press("enter")
    if text:
        time.sleep(1.0)
        pag.write(text, interval=0.05)


def _direct_calc(task_id, match, pag):
    expr = match.group(1).strip()
    tasks[task_id]["logs"].append(f"[{_time()}] 打开计算器")
    pag.hotkey("win")
    time.sleep(0.5)
    pag.write("calculator", interval=0.05)
    time.sleep(0.5)
    pag.press("enter")
    if expr:
        time.sleep(1.0)
        pag.write(expr, interval=0.05)
        pag.press("enter")


def _time():
    return time.strftime("%H:%M:%S")


# ---- Routes ----

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/run", methods=["POST"])
def api_run():
    data = request.get_json(force=True)
    instruction = data.get("task", "").strip()
    mode = data.get("mode", "agent")

    if not instruction:
        return jsonify({"error": "请输入指令"}), 400
    if mode not in ("agent", "direct"):
        return jsonify({"error": "模式必须是 agent 或 direct"}), 400

    task_id = str(uuid.uuid4())[:8]
    tasks[task_id] = {
        "status": "running",
        "logs": [],
        "instruction": instruction,
        "mode": mode,
        "created_at": _time(),
        "index": -1,  # for incremental log polling
    }

    t = threading.Thread(
        target=_capture_execution,
        args=(task_id, instruction, mode),
        daemon=True,
    )
    t.start()

    return jsonify({"task_id": task_id}), 202


@app.route("/api/status/<task_id>", methods=["GET"])
def api_status(task_id):
    task = tasks.get(task_id)
    if not task:
        return jsonify({"status": "not_found"}), 404

    # Return only new logs since last poll
    all_logs = task["logs"]
    last_index = request.args.get("index", -1, type=int)
    new_logs = all_logs[last_index + 1:]
    task["index"] = len(all_logs) - 1

    return jsonify({
        "status": task["status"],
        "logs": new_logs,
        "index": task["index"],
        "instruction": task["instruction"],
        "mode": task["mode"],
        "created_at": task["created_at"],
    })


@app.route("/api/tasks", methods=["GET"])
def api_tasks():
    result = []
    for tid, t in sorted(tasks.items(),
                          key=lambda x: x[1].get("created_at", ""),
                          reverse=True):
        result.append({
            "task_id": tid,
            "status": t["status"],
            "instruction": t["instruction"],
            "mode": t["mode"],
            "created_at": t["created_at"],
        })
    return jsonify(result[:20])  # latest 20


@app.route("/api/logs/<task_id>", methods=["GET"])
def api_logs(task_id):
    """Get full logs for a completed task."""
    task = tasks.get(task_id)
    if not task:
        return jsonify({"status": "not_found"}), 404
    return jsonify({
        "status": task["status"],
        "logs": task["logs"],
        "instruction": task["instruction"],
        "mode": task["mode"],
    })


if __name__ == "__main__":
    print(f"[Web Console] Starting on http://localhost:5000")
    print(f"[Web Console] Config: {CONFIG_PATH}")
    app.run(host="127.0.0.1", port=5000, debug=False)

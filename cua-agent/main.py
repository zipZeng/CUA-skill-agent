"""CUA-Skill 桌面 Agent — Tkinter GUI 入口。

双击运行此文件，输入自然语言指令，Agent 自动操作桌面完成任务。
"""

import queue
import threading
import time
from datetime import datetime

import tkinter as tk
from tkinter import messagebox, scrolledtext, ttk

from action_executor import ActionExecutor, StepLog
from agent_loop import AgentLoop
from config import Config
from intent_parser import IntentParser
from task_planner import TaskPlanner


class AgentApp:
    """桌面 Agent 主窗口。"""

    def __init__(self):
        self.config = Config()
        self.parser = IntentParser(self.config)
        self.planner = TaskPlanner(self.config)
        self.executor = ActionExecutor(self.config)

        self._running = False
        self._msg_queue = queue.Queue()

        self._build_ui()
        self._poll_queue()

    # ── UI 构建 ────────────────────────────────────────────────

    def _build_ui(self):
        self.root = tk.Tk()
        self.root.title("CUA-Skill 桌面 Agent")
        self.root.geometry("800x600")
        self.root.minsize(600, 400)

        # ── 顶部：指令输入区 ──
        top_frame = ttk.Frame(self.root, padding=8)
        top_frame.pack(fill=tk.X)

        ttk.Label(top_frame, text="指令:").pack(side=tk.LEFT)
        self.cmd_entry = ttk.Entry(top_frame, font=("", 11))
        self.cmd_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)
        self.cmd_entry.bind("<Return>", lambda e: self._start())
        self.cmd_entry.focus_set()

        self.btn_run = ttk.Button(top_frame, text="执行", command=self._start)
        self.btn_run.pack(side=tk.LEFT, padx=2)

        self.btn_stop = ttk.Button(top_frame, text="停止", command=self._stop, state=tk.DISABLED)
        self.btn_stop.pack(side=tk.LEFT)

        # ── 状态栏 ──
        status_frame = ttk.Frame(self.root, padding=(8, 0))
        status_frame.pack(fill=tk.X)

        self.status_label = ttk.Label(status_frame, text="● 就绪", foreground="green")
        self.status_label.pack(side=tk.LEFT)

        self.progress = ttk.Progressbar(status_frame, mode="determinate", length=200)
        self.progress.pack(side=tk.RIGHT, padx=4)

        self.time_label = ttk.Label(status_frame, text="")
        self.time_label.pack(side=tk.RIGHT, padx=8)

        # ── 日志区 ──
        log_frame = ttk.Frame(self.root, padding=8)
        log_frame.pack(fill=tk.BOTH, expand=True)

        self.log_area = scrolledtext.ScrolledText(
            log_frame,
            font=("Consolas", 9),
            wrap=tk.WORD,
            state=tk.DISABLED,
        )
        self.log_area.pack(fill=tk.BOTH, expand=True)

        # 颜色标签
        self.log_area.tag_config("ok", foreground="green")
        self.log_area.tag_config("fail", foreground="red")
        self.log_area.tag_config("info", foreground="gray")
        self.log_area.tag_config("bold", foreground="black")

        # ── 底部：已注册应用 ──
        bottom_frame = ttk.Frame(self.root, padding=(8, 4))
        bottom_frame.pack(fill=tk.X)
        apps = self.planner.list_apps()
        ttk.Label(bottom_frame, text=f"已注册应用: {', '.join(apps)}",
                  foreground="gray").pack(side=tk.LEFT)

    # ── 执行控制 ────────────────────────────────────────────────

    def _start(self):
        text = self.cmd_entry.get().strip()
        if not text:
            return
        if self._running:
            return

        self._running = True
        self.btn_run.config(state=tk.DISABLED)
        self.btn_stop.config(state=tk.NORMAL)
        self.progress.config(value=0)
        self.time_label.config(text="")

        self._log(f"用户指令: {text}", "info")

        thread = threading.Thread(target=self._worker, args=(text,), daemon=True)
        thread.start()

    def _stop(self):
        self._running = False
        self._log("用户取消了执行", "fail")

    # ── 后台工作线程 ────────────────────────────────────────────

    def _worker(self, text: str):
        t0 = time.time()

        # 1. 意图解析
        self._put_msg(("log", ("正在解析意图...", "info")))
        intent = self.parser.parse(text)
        self._put_msg(("log", (
            f"解析结果: action={intent.action}, app={intent.app}, query={intent.query}",
            "bold",
        )))

        if intent.action == "unknown":
            self._put_msg(("log", ("无法理解指令，请尝试更明确的说法", "fail")))
            self._put_msg(("done", None))
            return

        # 2. 任务规划
        self._put_msg(("log", ("正在规划任务...", "info")))
        steps, keywords = self.planner.plan(intent)
        self._put_msg(("log", (f"生成 {len(steps)} 个步骤, 窗口关键词: {keywords}", "info")))
        self._put_msg(("max_progress", len(steps)))

        if not steps:
            self._put_msg(("log", ("未生成可执行步骤", "fail")))
            self._put_msg(("done", None))
            return

        # 3. 逐步执行
        logs = []
        for step in steps:
            if not self._running:
                self._put_msg(("log", ("执行已取消", "fail")))
                break

            self._put_msg(("step_start", step))

            # Agent 模式：交给 AgentLoop 循环处理
            if step.type == "agent":
                self._run_agent_step(step, keywords, logs)
                continue

            # 执行单个 Step
            t_step = time.time()
            log = StepLog(step_index=len(logs), step_type=step.type)
            hwnd = None
            if keywords:
                hwnd = self.executor.wm.find_window(keywords)

            try:
                self.executor._execute_one(step, hwnd, log, keywords)
                log.elapsed_ms = int((time.time() - t_step) * 1000)
                self._put_msg(("step_ok", log))

            except Exception as e:
                log.error = str(e)
                log.elapsed_ms = int((time.time() - t_step) * 1000)
                self._put_msg(("step_fail", log))

                if not step.optional:
                    self._put_msg(("log", ("必要步骤失败，终止执行", "fail")))
                    break

            logs.append(log)

        total_ms = int((time.time() - t0) * 1000)
        self._put_msg(("log", (
            f"执行完成: {sum(1 for l in logs if l.success)}/{len(logs)} 成功, "
            f"总耗时 {total_ms / 1000:.1f}s",
            "bold",
        )))
        self._put_msg(("done", None))

    # ── Agent 模式 ──────────────────────────────────────────────

    def _run_agent_step(self, step, keywords, logs):
        """运行 Agent 循环，将每一步反映到 GUI 日志中。"""
        t_start = time.time()
        goal = step.text or ""
        self._put_msg(("log", (f"[Agent] 目标: {goal}", "bold")))

        if not self.executor.config.ollama_base_url:
            self._put_msg(("log", ("[Agent] Ollama 不可用，无法执行 Agent 任务", "fail")))
            log = StepLog(step_index=len(logs), step_type="agent",
                         error="Ollama 不可用", success=False)
            logs.append(log)
            return

        agent = AgentLoop(self.executor.wm, self.executor.locator,
                         self.executor.config)

        # 如果已找到窗口，先激活
        hwnd = None
        if keywords:
            hwnd = self.executor.wm.find_window(keywords)
            if hwnd:
                self.executor.wm.activate(hwnd)

        # 跟踪 Agent 内部步数
        agent_step_count = [0]

        def on_step(step_num, _action):
            agent_step_count[0] = step_num

        def on_done(message):
            pass

        result = agent.run(goal, on_step=on_step, on_done=on_done)

        elapsed_ms = int((time.time() - t_start) * 1000)
        success = not result.startswith("失败")

        if success:
            self._put_msg(("log", (
                f"[Agent] 完成: {result} ({agent_step_count[0]} 步, {elapsed_ms / 1000:.1f}s)",
                "ok",
            )))
        else:
            self._put_msg(("log", (f"[Agent] {result}", "fail")))

        log = StepLog(step_index=len(logs), step_type="agent",
                     elapsed_ms=elapsed_ms, success=success,
                     error="" if success else result)
        logs.append(log)

    # ── 消息队列（子线程 → GUI）────────────────────────────────

    def _put_msg(self, msg):
        self._msg_queue.put(msg)

    def _poll_queue(self):
        """每隔 100ms 检查消息队列，更新 UI。"""
        try:
            while True:
                msg = self._msg_queue.get_nowait()
                self._handle_msg(msg)
        except queue.Empty:
            pass
        self.root.after(100, self._poll_queue)

    def _handle_msg(self, msg):
        kind, data = msg
        if kind == "log":
            text, tag = data
            self._log(text, tag)
        elif kind == "max_progress":
            self.progress.config(maximum=data)
        elif kind == "step_start":
            step = data
            text = step_desc(step)
            self._log(f"→ {text}", "info")
            self.status_label.config(text="● 执行中", foreground="orange")
        elif kind == "step_ok":
            log = data
            self._log(f"  [OK] {log.elapsed_ms}ms @{log.found_coord}", "ok")
            self.progress.step(1)
        elif kind == "step_fail":
            log = data
            self._log(f"  [FAIL] {log.error}", "fail")
            self.progress.step(1)
        elif kind == "done":
            self._running = False
            self.btn_run.config(state=tk.NORMAL)
            self.btn_stop.config(state=tk.DISABLED)
            self.status_label.config(text="● 就绪", foreground="green")
            self.progress.config(value=0)

    def _log(self, text: str, tag: str = ""):
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_area.config(state=tk.NORMAL)
        line = f"[{ts}] {text}\n"
        self.log_area.insert(tk.END, line, tag)
        self.log_area.see(tk.END)
        self.log_area.config(state=tk.DISABLED)

    # ── 启动 ────────────────────────────────────────────────────

    def run(self):
        self.root.mainloop()


def step_desc(step) -> str:
    """生成步骤的可读描述。"""
    t = step.type
    if t == "launch":
        return f"启动应用: {step.text or ''}"
    if t == "click":
        return f"点击 \"{step.target}\""
    if t == "right_click":
        return f"右键 \"{step.target}\""
    if t == "double_click":
        return f"双击 \"{step.target}\""
    if t == "type":
        return f"输入 \"{step.text}\""
    if t == "hotkey":
        return f"组合键 {'+'.join(step.keys or [])}"
    if t == "press":
        return f"按键 {step.key}"
    if t == "wait":
        return f"等待 {step.seconds}s"
    if t == "scroll":
        return f"滚动 {step.text or ''}"
    if t == "agent":
        return f"AI Agent: {step.text or ''}"
    return str(t)


if __name__ == "__main__":
    app = AgentApp()
    app.run()

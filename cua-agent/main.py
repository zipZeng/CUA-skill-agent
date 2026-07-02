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

# ── 配色方案 ─────────────────────────────────────────────────

BG       = "#f0f2f5"   # 主背景
CARD_BG  = "#ffffff"   # 卡片背景
PRIMARY  = "#4f46e5"   # 主色调（按钮、强调）
SUCCESS  = "#16a34a"   # 成功
DANGER   = "#dc2626"   # 失败
WARN     = "#ea580c"   # 执行中
TEXT     = "#1e293b"   # 主文字
TEXT_SEC = "#64748b"   # 次要文字
LOG_BG   = "#1e293b"   # 日志区背景
LOG_OK   = "#4ade80"   # 日志-成功
LOG_FAIL = "#f87171"   # 日志-失败
LOG_INFO = "#94a3b8"   # 日志-信息

FONT_CJK = ("Microsoft YaHei UI", 11)
FONT_MONO = ("Cascadia Code", 10)


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
        self.root.geometry("1100x800")
        self.root.minsize(800, 600)
        self.root.configure(bg=BG)

        self._setup_styles()

        # 主容器
        main = tk.Frame(self.root, bg=BG)
        main.pack(fill=tk.BOTH, expand=True, padx=16, pady=16)

        # ── 标题栏 ──
        header = tk.Frame(main, bg=BG)
        header.pack(fill=tk.X, pady=(0, 12))
        tk.Label(header, text="CUA-Skill",
                 font=("Microsoft YaHei UI", 20, "bold"), fg=PRIMARY, bg=BG).pack(side=tk.LEFT)
        tk.Label(header, text="桌面 Agent",
                 font=("Microsoft YaHei UI", 20), fg=TEXT, bg=BG).pack(side=tk.LEFT, padx=(4, 0))

        # ── 输入卡片 ──
        input_card = tk.Frame(main, bg=CARD_BG, highlightthickness=1,
                              highlightbackground="#e2e8f0")
        input_card.pack(fill=tk.X, pady=(0, 10))

        # 输入区标题
        input_header = tk.Frame(input_card, bg=CARD_BG)
        input_header.pack(fill=tk.X, padx=14, pady=(12, 6))
        tk.Label(input_header, text="输入指令",
                 font=("Microsoft YaHei UI", 11, "bold"), fg=TEXT, bg=CARD_BG).pack(side=tk.LEFT)
        tk.Label(input_header, text="Enter 发送，支持复合指令与 Agent 模式",
                 font=(FONT_CJK[0], 9), fg=TEXT_SEC, bg=CARD_BG).pack(side=tk.LEFT, padx=8)

        # 多行输入框
        input_body = tk.Frame(input_card, bg=CARD_BG)
        input_body.pack(fill=tk.X, padx=14)
        self.cmd_entry = tk.Text(
            input_body,
            font=("Microsoft YaHei UI", 13),
            height=4,
            relief=tk.FLAT,
            wrap=tk.WORD,
            fg=TEXT,
            bg="#f8fafc",
            insertbackground=PRIMARY,
            selectbackground="#c7d2fe",
            padx=10, pady=10,
            borderwidth=1,
            highlightthickness=1,
            highlightbackground="#e2e8f0",
            highlightcolor=PRIMARY,
        )
        self.cmd_entry.pack(fill=tk.X)
        self.cmd_entry.bind("<Return>", self._on_enter)
        self.cmd_entry.bind("<Shift-Return>", lambda e: None)  # Shift+Enter 换行
        self.cmd_entry.focus_set()

        # 快捷指令标签
        quick_frame = tk.Frame(input_card, bg=CARD_BG)
        quick_frame.pack(fill=tk.X, padx=14, pady=(8, 12))
        tk.Label(quick_frame, text="快捷:", font=(FONT_CJK[0], 9),
                 fg=TEXT_SEC, bg=CARD_BG).pack(side=tk.LEFT)
        for label, cmd in [
            ("打开东方财富", "打开东方财富，点击游客登录"),
            ("沪深京排行", "打开东方财富，点击游客登录，再点击沪深京排行"),
            ("Agent模式", "帮我打开东方财富，点击游客登录，找到沪深京排行"),
        ]:
            btn = tk.Label(quick_frame, text=label, font=(FONT_CJK[0], 9),
                           fg=PRIMARY, bg=CARD_BG, cursor="hand2")
            btn.pack(side=tk.LEFT, padx=(8, 0))
            btn.bind("<Button-1>", lambda e, c=cmd: self._set_command(c))

        # ── 按钮栏 ──
        btn_bar = tk.Frame(main, bg=BG)
        btn_bar.pack(fill=tk.X, pady=(0, 8))

        self.btn_run = ttk.Button(btn_bar, text="▶  执行", command=self._start,
                                  style="Primary.TButton")
        self.btn_run.pack(side=tk.LEFT, padx=(0, 6))

        self.btn_stop = ttk.Button(btn_bar, text="■  停止", command=self._stop,
                                   state=tk.DISABLED, style="Danger.TButton")
        self.btn_stop.pack(side=tk.LEFT)

        # 状态指示器
        self.status_indicator = tk.Canvas(btn_bar, width=10, height=10,
                                          bg=BG, highlightthickness=0)
        self.status_indicator.pack(side=tk.LEFT, padx=(16, 4))
        self._draw_indicator(SUCCESS)

        self.status_label = tk.Label(btn_bar, text="就绪",
                                     font=(FONT_CJK[0], 10), fg=TEXT_SEC, bg=BG)
        self.status_label.pack(side=tk.LEFT)

        # 耗时
        self.time_label = tk.Label(btn_bar, text="", font=(FONT_CJK[0], 9),
                                    fg=TEXT_SEC, bg=BG)
        self.time_label.pack(side=tk.RIGHT, padx=(0, 8))

        # 进度
        self.progress = ttk.Progressbar(btn_bar, mode="determinate", length=160,
                                        style="TProgressbar")
        self.progress.pack(side=tk.RIGHT)

        # ── 日志卡片 ──
        log_card = tk.Frame(main, bg=CARD_BG, highlightthickness=1,
                           highlightbackground="#e2e8f0")
        log_card.pack(fill=tk.BOTH, expand=True, pady=(0, 8))

        log_header = tk.Frame(log_card, bg=CARD_BG)
        log_header.pack(fill=tk.X, padx=14, pady=(10, 6))
        tk.Label(log_header, text="执行日志",
                 font=("Microsoft YaHei UI", 11, "bold"), fg=TEXT, bg=CARD_BG).pack(side=tk.LEFT)

        # 日志文本框
        log_body = tk.Frame(log_card, bg=CARD_BG)
        log_body.pack(fill=tk.BOTH, expand=True, padx=14, pady=(0, 12))

        self.log_area = tk.Text(
            log_body,
            font=FONT_MONO,
            wrap=tk.WORD,
            state=tk.DISABLED,
            relief=tk.FLAT,
            fg="#cbd5e1",
            bg=LOG_BG,
            insertbackground="#cbd5e1",
            selectbackground="#334155",
            padx=12, pady=10,
        )
        self.log_area.pack(fill=tk.BOTH, expand=True)

        # 日志颜色标签
        self.log_area.tag_config("ok", foreground=LOG_OK)
        self.log_area.tag_config("fail", foreground=LOG_FAIL)
        self.log_area.tag_config("info", foreground=LOG_INFO)
        self.log_area.tag_config("bold", foreground="#e2e8f0",
                                 font=(FONT_MONO[0], FONT_MONO[1], "bold"))

        # ── 底部 ──
        footer = tk.Frame(main, bg=BG)
        footer.pack(fill=tk.X)
        apps = self.planner.list_apps()
        tk.Label(footer, text=f"已注册: {', '.join(apps)}",
                 font=(FONT_CJK[0], 8), fg=TEXT_SEC, bg=BG).pack(side=tk.LEFT)

    def _setup_styles(self):
        """配置 ttk 样式。"""
        style = ttk.Style()
        style.theme_use('clam')

        style.configure("Primary.TButton",
                        font=("Microsoft YaHei UI", 10, "bold"),
                        background=PRIMARY, foreground="white",
                        borderwidth=0, padding=(20, 8))
        style.map("Primary.TButton",
                  background=[("active", "#4338ca"), ("disabled", "#c7d2fe")],
                  foreground=[("disabled", "#e2e8f0")])

        style.configure("Danger.TButton",
                        font=("Microsoft YaHei UI", 10, "bold"),
                        background="white", foreground=DANGER,
                        borderwidth=1, padding=(20, 8))
        style.map("Danger.TButton",
                  background=[("active", "#fef2f2")])

        style.configure("TProgressbar", thickness=5, background=PRIMARY,
                        troughcolor="#e2e8f0", borderwidth=0)

    def _draw_indicator(self, color: str):
        self.status_indicator.delete("all")
        r = 4
        self.status_indicator.create_oval(1, 1, 2*r+1, 2*r+1,
                                          fill=color, outline=color)

    def _on_enter(self, event):
        """Enter 键发送，Shift+Enter 换行。"""
        if event.state & 1:   # Shift pressed
            return None
        self._start()
        return "break"         # 阻止默认换行

    def _set_command(self, text: str):
        """快捷指令按钮：填入输入框。"""
        self.cmd_entry.delete("1.0", tk.END)
        self.cmd_entry.insert("1.0", text)

    # ── 执行控制 ────────────────────────────────────────────────

    def _start(self):
        text = self.cmd_entry.get("1.0", tk.END).strip()
        if not text:
            return
        if self._running:
            return

        self._running = True
        self.btn_run.config(state=tk.DISABLED)
        self.btn_stop.config(state=tk.NORMAL)
        self.progress.config(value=0)
        self.time_label.config(text="")

        self._log(f"▸ {text}", "bold")

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
            f"解析: action={intent.action}, app={intent.app}",
            "info",
        )))

        if intent.action == "unknown":
            self._put_msg(("log", ("无法理解指令", "fail")))
            self._put_msg(("done", None))
            return

        # 2. 任务规划
        self._put_msg(("log", ("正在规划任务...", "info")))
        steps, keywords = self.planner.plan(intent)
        self._put_msg(("log", (f"规划: {len(steps)} 步, 窗口关键词: {keywords}", "info")))
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

            # Agent 模式
            if step.type == "agent":
                self._run_agent_step(step, keywords, logs)
                continue

            # 常规步骤
            t_step = time.time()
            log = StepLog(step_index=len(logs), step_type=step.type)
            hwnd = None
            if keywords:
                hwnd = self.executor.wm.find_window(keywords)

            try:
                self.executor._execute_one(step, hwnd, log, keywords,
                                           should_stop=lambda: not self._running)
                log.elapsed_ms = int((time.time() - t_step) * 1000)
                self._put_msg(("step_ok", log))

            except Exception as e:
                log.error = str(e)
                log.elapsed_ms = int((time.time() - t_step) * 1000)
                self._put_msg(("step_fail", log))

                if not self._running:
                    self._put_msg(("log", ("执行已取消", "fail")))
                    break
                if not step.optional:
                    self._put_msg(("log", ("必要步骤失败，终止执行", "fail")))
                    break

            logs.append(log)

        total_ms = int((time.time() - t0) * 1000)
        ok_count = sum(1 for l in logs if l.success)
        self._put_msg(("log", (
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"完成: {ok_count}/{len(logs)} 成功, 总耗时 {total_ms / 1000:.1f}s",
            "bold",
        )))
        self._put_msg(("done", None))

    # ── Agent 模式 ──────────────────────────────────────────────

    def _run_agent_step(self, step, keywords, logs):
        """运行 Agent 循环。"""
        t_start = time.time()
        goal = step.text or ""
        self._put_msg(("log", (f"[Agent] 目标: {goal}", "bold")))

        if not self.executor.config.ollama_base_url:
            self._put_msg(("log", ("[Agent] Ollama 不可用", "fail")))
            log = StepLog(step_index=len(logs), step_type="agent",
                         error="Ollama 不可用", success=False)
            logs.append(log)
            return

        agent = AgentLoop(self.executor.wm, self.executor.locator,
                         self.executor.config)

        hwnd = None
        if keywords:
            hwnd = self.executor.wm.find_window(keywords)
            if hwnd:
                self.executor.wm.activate(hwnd)

        agent_step_count = [0]

        def on_step(step_num, _action):
            agent_step_count[0] = step_num
            self._put_msg(("log", (f"  [Agent] 第{step_num}步...", "info")))

        def on_done(message):
            pass

        result = agent.run(goal, on_step=on_step, on_done=on_done,
                          should_stop=lambda: not self._running)

        elapsed_ms = int((time.time() - t_start) * 1000)
        success = not result.startswith("失败")

        if success:
            self._put_msg(("log", (
                f"[Agent] 完成: {result} ({agent_step_count[0]}步, {elapsed_ms / 1000:.1f}s)",
                "ok",
            )))
        else:
            self._put_msg(("log", (f"[Agent] {result}", "fail")))

        log = StepLog(step_index=len(logs), step_type="agent",
                     elapsed_ms=elapsed_ms, success=success,
                     error="" if success else result)
        logs.append(log)

    # ── 消息队列（子线程 → GUI） ────────────────────────────────

    def _put_msg(self, msg):
        self._msg_queue.put(msg)

    def _poll_queue(self):
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
            self._log(f"  → {step_desc(step)}", "info")
            self.status_label.config(text="执行中", fg=WARN)
            self._draw_indicator(WARN)
        elif kind == "step_ok":
            log = data
            self._log(f"    ✓ {log.elapsed_ms}ms @{log.found_coord}", "ok")
            self.progress.step(1)
        elif kind == "step_fail":
            log = data
            self._log(f"    ✗ {log.error}", "fail")
            self.progress.step(1)
        elif kind == "done":
            self._running = False
            self.btn_run.config(state=tk.NORMAL)
            self.btn_stop.config(state=tk.DISABLED)
            self.status_label.config(text="就绪", fg=TEXT_SEC)
            self._draw_indicator(SUCCESS)
            self.progress.config(value=0)

    def _log(self, text: str, tag: str = ""):
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_area.config(state=tk.NORMAL)
        self.log_area.insert(tk.END, f"[{ts}] {text}\n", tag)
        self.log_area.see(tk.END)
        self.log_area.config(state=tk.DISABLED)

    # ── 启动 ────────────────────────────────────────────────────

    def run(self):
        self.root.mainloop()


def step_desc(step) -> str:
    """生成步骤的可读描述。"""
    t = step.type
    if t == "launch":     return f"启动: {step.text or ''}"
    if t == "click":      return f"点击 \"{step.target}\""
    if t == "right_click": return f"右键 \"{step.target}\""
    if t == "double_click": return f"双击 \"{step.target}\""
    if t == "type":       return f"输入 \"{step.text}\""
    if t == "hotkey":     return f"组合键 {'+'.join(step.keys or [])}"
    if t == "press":      return f"按键 {step.key}"
    if t == "wait":       return f"等待 {step.seconds}s"
    if t == "scroll":     return f"滚动 {step.text or ''}"
    if t == "agent":      return f"AI Agent: {step.text or ''}"
    return str(t)


if __name__ == "__main__":
    app = AgentApp()
    app.run()

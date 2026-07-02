"""动作执行器 — 逐步执行 Step 序列，非独占模式 + 日志 + 重试。

架构:
    for each Step:
        1. 截图（激活前或释放后）
        2. OCR 定位目标
        3. 激活窗口 → 执行动作 → 释放焦点
        4. 记录 StepLog
"""

import os
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from config import Config
from element_locator import ElementLocator
from window_manager import WindowManager


@dataclass
class Step:
    """任务规划器输出的一步操作。"""
    type: str              # launch|click|right_click|double_click|type|hotkey|press|wait|scroll
    target: str = None     # OCR 查找的目标文字
    text: str = None       # 要输入的文字
    keys: list = None      # 组合键
    key: str = None        # 单键
    seconds: float = None  # 等待秒数
    fallback: list = None  # 备选目标文字（依次尝试）
    optional: bool = False # 失败是否跳过继续
    repeat: int = 1        # 重复次数


@dataclass
class StepLog:
    """单步执行日志。"""
    step_index: int
    step_type: str
    screenshot_path: str = ""
    ocr_results: list = field(default_factory=list)
    target_text: str = ""
    found_coord: tuple = None
    clicked_coord: tuple = None
    elapsed_ms: int = 0
    success: bool = False
    error: str = ""


class ActionExecutor:
    """逐步执行 Step 序列，非独占模式。"""

    def __init__(self, config: Config = None):
        self.config = config or Config()
        self.wm = WindowManager(self.config)
        self.locator = ElementLocator(self.config)
        self._ensure_dirs()

    def _ensure_dirs(self):
        os.makedirs(self.config.screenshot_dir, exist_ok=True)
        os.makedirs(self.config.log_dir, exist_ok=True)

    # ── 主入口 ─────────────────────────────────────────────────

    def execute(self, steps: list[Step], app_keywords: list[str] = None) -> list[StepLog]:
        """执行步骤序列，返回日志列表。"""

        logs: list[StepLog] = []
        hwnd = None

        # 先尝试找到目标窗口
        if app_keywords:
            hwnd = self.wm.find_window(app_keywords)
            if hwnd:
                self.locator.update_screen_size(*self._screen_size())

        for i, step in enumerate(steps):
            t0 = time.time()
            log = StepLog(step_index=i, step_type=step.type)

            try:
                self._execute_one(step, hwnd, log, app_keywords)
            except Exception as e:
                log.error = str(e)
                log.success = False

            log.elapsed_ms = int((time.time() - t0) * 1000)

            # 重复执行
            if step.repeat > 1 and log.success:
                for _ in range(step.repeat - 1):
                    try:
                        self._execute_one(step, hwnd, StepLog(step_index=i, step_type=step.type), app_keywords)
                    except Exception:
                        pass

            logs.append(log)

            # 失败处理
            if not log.success:
                if step.optional:
                    continue  # 跳过可选步骤的失败
                else:
                    break     # 必要步骤失败则终止

        return logs

    def _execute_one(self, step: Step, hwnd: int | None, log: StepLog,
                     app_keywords: list[str] = None):
        """执行单个 Step。"""

        # ── 需要 OCR 定位的步骤 ──
        if step.type in ("click", "right_click", "double_click"):
            log.target_text = step.target
            log.screenshot_path = self._screenshot()

            # OCR 定位
            img = self.wm.screenshot()
            coord = self.locator.find_text(img, step.target, step.fallback)

            if not coord:
                # 策略3预留：视觉模型兜底
                raise RuntimeError(f"未找到目标: '{step.target}'")

            log.found_coord = coord

            # 激活 → 点击 → 释放
            if hwnd:
                self.wm.activate(hwnd)
                time.sleep(0.1)

            if step.type == "click":
                self.wm.click(*coord)
            elif step.type == "right_click":
                self.wm.right_click(*coord)
            elif step.type == "double_click":
                self.wm.double_click(*coord)

            log.clicked_coord = coord
            time.sleep(self.config.post_action_delay)

            if hwnd:
                self.wm.release()

        # ── 键盘输入 ──
        elif step.type == "type":
            self.wm.type_text(step.text)
            time.sleep(self.config.post_action_delay)

        # ── 组合键 ──
        elif step.type == "hotkey":
            self.wm.hotkey(*step.keys)
            time.sleep(self.config.post_action_delay)

        # ── 单键 ──
        elif step.type == "press":
            self.wm.press(step.key)
            time.sleep(self.config.post_action_delay)

        # ── 等待 ──
        elif step.type == "wait":
            self.wm.wait(step.seconds or 1.0)

        # ── 启动应用 ──
        elif step.type == "launch":
            self.wm.launch(step.text, app_keywords,
                          ocr_locator=self.locator)
            time.sleep(self.config.post_action_delay)

        # ── 滚动 ──
        elif step.type == "scroll":
            if step.target:
                img = self.wm.screenshot()
                coord = self.locator.find_text(img, step.target)
                if coord:
                    self.wm.click(*coord)
                    time.sleep(0.1)
            import pyautogui
            pyautogui.scroll(step.text or -3)

        log.success = True

    # ── 截图工具 ───────────────────────────────────────────────

    def _screenshot(self) -> str:
        """截图并保存，返回文件路径。"""
        ts = datetime.now().strftime("%H%M%S_%f")[:-3]
        path = os.path.join(self.config.screenshot_dir, f"step_{ts}.png")
        self.wm.screenshot().save(path)
        return path

    def _screen_size(self) -> tuple[int, int]:
        """返回当前屏幕宽高。"""
        img = self.wm.screenshot()
        return img.size

    # ── 日志输出 ───────────────────────────────────────────────

    def log_summary(self, logs: list[StepLog]) -> str:
        """生成执行摘要文本。"""
        total = len(logs)
        ok = sum(1 for l in logs if l.success)
        total_ms = sum(l.elapsed_ms for l in logs)
        lines = [
            f"执行完成: {ok}/{total} 成功, 总耗时 {total_ms / 1000:.1f}s",
            "-" * 60,
        ]
        for l in logs:
            status = "OK" if l.success else "FAIL"
            target = f" → '{l.target_text}'" if l.target_text else ""
            coord = f" @{l.found_coord}" if l.found_coord else ""
            err = f" | {l.error}" if l.error else ""
            lines.append(
                f"  [{status}] step {l.step_index} {l.step_type}{target}{coord} "
                f"({l.elapsed_ms}ms){err}"
            )
        return "\n".join(lines)

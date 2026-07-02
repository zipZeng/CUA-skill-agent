"""Agent 循环 — 截图→OCR→模型决策→执行→重复。

替代模板系统的开放式任务执行方式。模型"看着"屏幕逐步决策，
适用于步骤数量不确定、需要根据屏幕反馈动态调整的复杂任务。

用法:
    loop = AgentLoop(window_manager, element_locator, config)
    result = loop.run("下载东方财富沪深京下所有子板块数据")
"""

import json
import re
import time

import requests

from config import Config
from element_locator import ElementLocator
from window_manager import WindowManager

# 每步最多允许的 OCR 文字数（截断发给模型，节省 context）
MAX_OCR_ITEMS = 80

# 最多执行步数（防止死循环）
MAX_STEPS = 30

AGENT_SYSTEM_PROMPT = """你是一个 Windows 桌面自动化助手。你能"看到"屏幕上的文字及其坐标，根据用户目标逐步操作。

## 可用操作

返回 JSON，每次一个操作：
- {"action": "click", "target": "文字"}          — 左键点击
- {"action": "right_click", "target": "文字"}    — 右键点击
- {"action": "double_click", "target": "文字"}   — 双击
- {"action": "type", "text": "内容"}              — 输入文字
- {"action": "hotkey", "keys": ["ctrl", "c"]}     — 组合键
- {"action": "press", "key": "enter"}             — 按单键
- {"action": "scroll", "amount": -3}              — 滚动（负数=向下，正数=向上）
- {"action": "wait", "seconds": 2}                — 等待秒数
- {"action": "done", "message": "完成了什么"}      — 任务完成
- {"action": "fail", "reason": "原因"}             — 无法完成

## 重要规则

1. **严格按照用户目标中的文字操作**。如用户说"点击游客登录"，就找"游客登录"，不要选"通行证登录"或其他
2. target 必须从屏幕文字中精确选择，不要编造不存在的文字
3. 找不到目标文字时，先 scroll 向下滚动再找，不要选相近但不对的文字
4. 弹窗/广告优先关闭（找"关闭""×""取消""我知道了"）
5. 不要点击窗口菜单栏（y < 50 的文字），要操作 y > 100 的页面主体内容
6. 如果重复操作同一位置 2 次无效，换一种方式，不要继续重复
7. 每步只做一个操作，任务完成后返回 done
8. 只返回 JSON，不要其他文字"""


class AgentLoop:
    """基于 LLM 的开放式 Agent 执行循环。"""

    def __init__(self, wm: WindowManager, locator: ElementLocator,
                 config: Config = None):
        self.wm = wm
        self.locator = locator
        self.config = config or Config

    def run(self, goal: str,
            on_step: callable = None,
            on_done: callable = None,
            should_stop: callable = None) -> str:
        """执行 Agent 循环，返回最终消息。

        on_step(step_num, action_json) — 每步执行前回调
        on_done(message)               — 完成时回调
        should_stop() → bool           — 返回 True 时中止循环
        """
        history: list[dict] = []
        last_ocr_texts: list[str] = []

        # 从目标中提取关键词，用于 OCR 采样加权
        goal_keywords = self._extract_keywords(goal)

        for step_num in range(1, MAX_STEPS + 1):
            if should_stop and should_stop():
                print("[Agent] 用户取消")
                if on_done:
                    on_done("用户取消")
                return "用户取消"

            # 1. 截图 + OCR
            img = self.wm.screenshot()
            all_texts = self.locator._ocr_recognize(img)

            # 均匀采样，但保留包含目标关键词的项
            if len(all_texts) > MAX_OCR_ITEMS:
                all_texts.sort(key=lambda x: x[1][1])  # 按 y 排序
                # 先提取匹配关键词的项（最多 20 个）
                boosted = [t for t in all_texts
                          if any(kw in t[0] for kw in goal_keywords)]
                boosted = boosted[:20]
                # 剩余名额均匀采样
                remaining = MAX_OCR_ITEMS - len(boosted)
                others = [t for t in all_texts if t not in boosted]
                if len(others) > remaining:
                    gap = len(others) / remaining
                    others = [others[int(i * gap)] for i in range(remaining)]
                all_texts = boosted + others

            ocr_lines = []
            for text, (x1, y1, x2, y2) in all_texts:
                cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
                ocr_lines.append(f'  "{text}" @({cx}, {cy})')
            ocr_block = "\n".join(ocr_lines)

            # 调试输出
            if boosted:
                print(f"[Agent OCR] 采样 {len(all_texts)} 项 (含 {len(boosted)} 项关键词匹配), 前15个:")
            else:
                print(f"[Agent OCR] 采样 {len(all_texts)} 项, 前15个:")
            for line in ocr_lines[:15]:
                print(line)

            # 2. 构建 prompt
            history_text = self._format_history(history[-6:])

            user_prompt = f"""用户目标: {goal}

屏幕可见文字及坐标:
{ocr_block}

最近操作:
{history_text if history_text else "（无）"}

请决定下一步操作（只返回 JSON）："""

            # 3. 调用模型
            if on_step:
                on_step(step_num, None)

            if should_stop and should_stop():
                print("[Agent] 用户取消 (模型调用前)")
                if on_done:
                    on_done("用户取消")
                return "用户取消"

            response = self._call_model(user_prompt)

            if should_stop and should_stop():
                print("[Agent] 用户取消 (模型调用后)")
                if on_done:
                    on_done("用户取消")
                return "用户取消"

            action = self._parse_response(response)

            if action is None:
                print(f"[Agent] 模型返回无效 JSON，重试: {response[:200]}")
                continue

            print(f"[Agent] Step {step_num}: {json.dumps(action, ensure_ascii=False)}")

            # 4. 检查终止
            if action.get("action") == "done":
                msg = action.get("message", "完成")
                print(f"[Agent] 任务完成: {msg}")
                if on_done:
                    on_done(msg)
                return msg

            if action.get("action") == "fail":
                reason = action.get("reason", "未知原因")
                print(f"[Agent] 任务失败: {reason}")
                if on_done:
                    on_done(f"失败: {reason}")
                return f"失败: {reason}"

            # 5. 执行操作
            try:
                self._execute_action(action)
                history.append(action)
            except Exception as e:
                print(f"[Agent] 执行失败: {e}")
                history.append({"error": str(e)})

            time.sleep(self.config.post_action_delay)

        # 达到最大步数
        msg = f"达到最大步数 {MAX_STEPS}"
        print(f"[Agent] {msg}")
        if on_done:
            on_done(msg)
        return msg

    # ── 模型调用 ────────────────────────────────────────────────

    def _call_model(self, user_prompt: str) -> str:
        """调用 Ollama 模型，返回响应文本。"""
        try:
            resp = requests.post(
                f"{self.config.ollama_base_url}/api/chat",
                json={
                    "model": self.config.text_model,
                    "messages": [
                        {"role": "system", "content": AGENT_SYSTEM_PROMPT},
                        {"role": "user", "content": user_prompt},
                    ],
                    "stream": False,
                    "options": {"temperature": 0.1},
                },
                timeout=30,
            )
            data = resp.json()
            return data.get("message", {}).get("content", "")
        except Exception as e:
            print(f"[Agent] 模型调用失败: {e}")
            return ""

    def _parse_response(self, text: str) -> dict | None:
        """从模型响应中解析 JSON 操作。"""
        if not text:
            return None
        # 提取 JSON 块
        match = re.search(r'\{[^{}]*\}', text)
        if not match:
            return None
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            return None

    # ── 操作执行 ────────────────────────────────────────────────

    def _execute_action(self, action: dict):
        """执行单个操作。"""
        act = action.get("action", "")

        if act == "click":
            target = action.get("target", "")
            if not target:
                raise ValueError("click 需要 target")
            coord = self._find_target(target)
            self.wm.click(*coord)

        elif act == "right_click":
            target = action.get("target", "")
            if not target:
                raise ValueError("right_click 需要 target")
            coord = self._find_target(target)
            self.wm.right_click(*coord)

        elif act == "double_click":
            target = action.get("target", "")
            if not target:
                raise ValueError("double_click 需要 target")
            coord = self._find_target(target)
            self.wm.double_click(*coord)

        elif act == "type":
            text = action.get("text", "")
            if not text:
                raise ValueError("type 需要 text")
            self.wm.type_text(text)

        elif act == "hotkey":
            keys = action.get("keys", [])
            if not keys:
                raise ValueError("hotkey 需要 keys")
            self.wm.hotkey(*keys)

        elif act == "press":
            key = action.get("key", "")
            if not key:
                raise ValueError("press 需要 key")
            self.wm.press(key)

        elif act == "scroll":
            amount = action.get("amount", -3)
            import pyautogui
            pyautogui.scroll(amount)

        elif act == "wait":
            seconds = action.get("seconds", 1)
            self.wm.wait(seconds)

        elif act in ("done", "fail"):
            pass  # 在 run() 中处理

        else:
            raise ValueError(f"未知操作: {act}")

    def _find_target(self, target: str) -> tuple[int, int]:
        """在当前屏幕上 OCR 定位目标文字，返回坐标。"""
        img = self.wm.screenshot()
        coord = self.locator.find_text(img, target)
        if not coord:
            raise RuntimeError(f"未找到目标: '{target}'")
        return coord

    def _extract_keywords(self, goal: str) -> list[str]:
        """从目标文本中提取关键词，用于 OCR 采样加权。"""
        stop = {'帮我', '打开', '点击', '找到', '下载', '所有', '数据', '到',
                '的', '在', '了', '，', '再', '然后', '本地', '和', '请',
                '一个', '这个', '那个', '里面', '下面', '上面', '把', '用'}
        words = re.findall(r'[一-鿿\w]+', goal)
        return [w for w in words if w not in stop and len(w) >= 2]

    # ── 工具 ────────────────────────────────────────────────────

    def _format_history(self, actions: list[dict]) -> str:
        """格式化操作历史为文本。"""
        lines = []
        for i, act in enumerate(actions, 1):
            if "error" in act:
                lines.append(f"  {i}. 错误: {act['error']}")
            else:
                a = act.get("action", "?")
                if a in ("click", "right_click", "double_click"):
                    lines.append(f"  {i}. {a} \"{act.get('target', '')}\"")
                elif a == "type":
                    lines.append(f"  {i}. type \"{act.get('text', '')}\"")
                elif a == "hotkey":
                    lines.append(f"  {i}. hotkey {act.get('keys', [])}")
                elif a == "press":
                    lines.append(f"  {i}. press \"{act.get('key', '')}\"")
                elif a == "scroll":
                    lines.append(f"  {i}. scroll {act.get('amount', 0)}")
                elif a == "wait":
                    lines.append(f"  {i}. wait {act.get('seconds', 0)}s")
                else:
                    lines.append(f"  {i}. {a}")
        return "\n".join(lines)

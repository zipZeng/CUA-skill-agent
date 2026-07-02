"""非独占式窗口管理器 — 查找/激活/释放/截图/点击/输入。
只依赖 win32gui + pyautogui，不引入 UIA/pywinauto。
"""

import time

import pyautogui
import win32con
import win32gui
from PIL import Image

from config import Config


class WindowManager:
    """非独占式窗口管理。核心模式：激活→操作→释放。"""

    def __init__(self, config: Config = None):
        self.config = config or Config()
        self._target_hwnd: int | None = None

    # ── 窗口查找 ──────────────────────────────────────────────

    def _enum_visible(self) -> list[tuple[int, str]]:
        """枚举所有可见且有标题的窗口，返回 [(hwnd, title), ...]。"""
        result = []

        def callback(hwnd, _extra):
            if win32gui.IsWindowVisible(hwnd):
                title = win32gui.GetWindowText(hwnd)
                if title:
                    result.append((hwnd, title))
        win32gui.EnumWindows(callback, None)
        return result

    def find_window(self, title_keywords: list[str]) -> int | None:
        """扫描所有可见窗口，匹配标题关键词（任一命中即返回），返回句柄。"""
        windows = self._enum_visible()
        for hwnd, title in windows:
            title_lower = title.lower()
            for kw in title_keywords:
                if kw.lower() in title_lower:
                    self._target_hwnd = hwnd
                    return hwnd
        return None

    def find_window_by_class(self, class_name: str) -> int | None:
        """按窗口类名查找。"""
        windows = self._enum_visible()
        for hwnd, _title in windows:
            if win32gui.GetClassName(hwnd) == class_name:
                return hwnd
        return None

    def list_windows(self) -> list[str]:
        """返回当前所有可见窗口标题。"""
        return [title for _hwnd, title in self._enum_visible()]

    # ── 启动应用 ──────────────────────────────────────────────

    def launch(self, app_name: str, keywords: list[str] = None,
               wait_seconds: float = None, ocr_locator=None,
               should_stop: callable = None) -> bool:
        """启动应用：先查窗口是否已存在，再桌面图标 OCR 双击，最后开始菜单兜底。"""
        if wait_seconds is None:
            wait_seconds = self.config.window_load_delay

        search_names = keywords or [app_name]

        # 1. 检查窗口是否已存在
        hwnd = self.find_window(search_names)
        if hwnd:
            self._target_hwnd = hwnd
            self.activate(hwnd)
            print(f"[Launch] 窗口已打开 hwnd={hwnd}")
            return True

        # 2. 桌面图标 OCR → 双击
        print(f"[Launch] 窗口未打开，尝试桌面图标 OCR, keywords={search_names}")
        if self._launch_by_desktop_icon(search_names, wait_seconds, ocr_locator, should_stop):
            print(f"[Launch] 桌面图标启动成功")
            return True

        if should_stop and should_stop():
            raise RuntimeError("用户取消")

        # 3. 开始菜单兜底
        print(f"[Launch] 桌面未找到图标，回退到开始菜单搜索")
        pyautogui.hotkey("win")
        self._sleep(0.3, should_stop)
        pyautogui.write(app_name, interval=0.05)
        self._sleep(0.5, should_stop)
        pyautogui.press("enter")
        self._sleep(wait_seconds, should_stop)
        return True

    def _launch_by_desktop_icon(self, keywords: list[str],
                                 wait_seconds: float,
                                 ocr_locator=None,
                                 should_stop: callable = None) -> bool:
        """显示桌面 → OCR 找图标文字 → 双击启动。"""
        from element_locator import ElementLocator

        # 显示桌面
        pyautogui.hotkey("win", "d")
        self._sleep(0.5, should_stop)

        img = self.screenshot()
        locator = ocr_locator or ElementLocator(self.config, *img.size)
        print(f"[Desktop OCR] 截图 {img.size}, 查找: {keywords}")

        if should_stop and should_stop():
            raise RuntimeError("用户取消")

        # 收集所有 OCR 识别结果
        all_texts = locator._ocr_recognize(img)
        top_texts = sorted(
            [(t, ((x1+x2)//2, (y1+y2)//2)) for t, (x1,y1,x2,y2) in all_texts],
            key=lambda x: x[1][1]  # sort by y
        )[:30]
        print(f"[Desktop OCR] 识别到 {len(all_texts)} 个文字项，前30个:")
        for t, pos in top_texts:
            print(f"  \"{t}\" @ {pos}")

        # 在所有 OCR 结果中找最佳匹配（避免模糊匹配造成的误点击）
        best_kw, best_coord, best_score = None, None, 0.0
        for ocr_text, (x1, y1, x2, y2) in all_texts:
            for kw in keywords:
                score = locator._match_score(kw, ocr_text)
                if score > best_score:
                    best_score = score
                    best_kw = kw
                    best_coord = ((x1 + x2) // 2, (y1 + y2) // 2)

        if best_coord and best_score >= 0.9:
            print(f"[Desktop OCR] 最佳匹配 \"{best_kw}\" @ {best_coord} (score={best_score:.2f}), 双击启动")
            self.double_click(*best_coord)
            self._sleep(wait_seconds, should_stop)
            hwnd = self.find_window(keywords)
            if hwnd:
                self._target_hwnd = hwnd
                return True
            pyautogui.hotkey("win", "d")
            self._sleep(0.3, should_stop)
        elif best_coord:
            print(f"[Desktop OCR] 匹配度过低 \"{best_kw}\" score={best_score:.2f} < 0.9, 跳过")
        else:
            print(f"[Desktop OCR] 未找到任何匹配")

        return False

    # ── 窗口激活/释放 ─────────────────────────────────────────

    def activate(self, hwnd: int = None) -> bool:
        """激活窗口（恢复最小化 + 置顶）。"""
        hwnd = hwnd or self._target_hwnd
        if not hwnd:
            return False
        if win32gui.IsIconic(hwnd):
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        try:
            win32gui.SetForegroundWindow(hwnd)
        except Exception:
            pass
        time.sleep(0.1)
        return True

    def release(self) -> None:
        """Alt+Tab 切走，释放焦点给用户。"""
        pyautogui.hotkey("alt", "tab")
        time.sleep(0.1)

    # ── 截图 ──────────────────────────────────────────────────

    def screenshot(self) -> Image.Image:
        """全屏截图，返回 PIL Image 供 OCR 分析。"""
        return pyautogui.screenshot()

    # ── 鼠标操作 ──────────────────────────────────────────────

    def click(self, x: int, y: int, button: str = "left") -> None:
        """在绝对屏幕坐标点击（先移动再点击，确保动作可见）。"""
        print(f"[Click] {button} @({x}, {y})")
        pyautogui.moveTo(x, y, duration=0.15)
        time.sleep(0.05)
        pyautogui.click(x, y, button=button)

    def right_click(self, x: int, y: int) -> None:
        """右键点击。"""
        print(f"[Click] right @({x}, {y})")
        pyautogui.moveTo(x, y, duration=0.15)
        time.sleep(0.05)
        pyautogui.click(x, y, button="right")

    def double_click(self, x: int, y: int) -> None:
        """双击。"""
        print(f"[Click] double @({x}, {y})")
        pyautogui.moveTo(x, y, duration=0.15)
        time.sleep(0.05)
        pyautogui.doubleClick(x, y)

    # ── 键盘操作 ──────────────────────────────────────────────

    def type_text(self, text: str) -> None:
        """剪贴板粘贴（绕过中文输入法）。"""
        from lib.ime_utils import type_unicode
        type_unicode(text)

    def hotkey(self, *keys: str) -> None:
        """组合键。例: hotkey('ctrl', 'a')"""
        pyautogui.hotkey(*keys)

    def press(self, key: str) -> None:
        """按单键。"""
        pyautogui.press(key)

    # ── 等待 ──────────────────────────────────────────────────

    def _sleep(self, seconds: float, should_stop: callable = None):
        """分段 sleep，每 0.1s 检查停止标志。"""
        remaining = seconds
        while remaining > 0:
            if should_stop and should_stop():
                raise RuntimeError("用户取消")
            chunk = min(0.1, remaining)
            time.sleep(chunk)
            remaining -= chunk

    def wait(self, seconds: float) -> None:
        """等待指定秒数。"""
        time.sleep(seconds)

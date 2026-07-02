"""元素定位器 — 3级策略：OCR → 模板坐标 → 视觉模型（兜底）。

核心 API:
    locator = ElementLocator(config)
    x, y = locator.find_text("数据导出")         # 返回屏幕坐标
    x, y = locator.find_text("确定", fallback=["确认", "OK"])
    x, y = locator.wait_for_text("数据导出", timeout=10.0)
"""

import difflib
import time
from typing import Optional

import numpy as np
from PIL import Image

from config import Config

# ── 模板坐标库（相对屏幕比例，自适应分辨率）───────────────────

TEMPLATE_POSITIONS: dict[str, tuple[float, float]] = {
    # 窗口控制
    "关闭":   (0.95, 0.02),
    "×":     (0.95, 0.02),
    "最小化": (0.90, 0.02),
    "最大化": (0.93, 0.02),
    # 菜单栏
    "文件":   (0.05, 0.03),
    "编辑":   (0.08, 0.03),
    "查看":   (0.11, 0.03),
    "工具":   (0.16, 0.03),
    "帮助":   (0.20, 0.03),
    # 浏览器
    "地址栏": (0.50, 0.08),
    "搜索框": (0.50, 0.10),
    # 对话框
    "确定":   (0.50, 0.85),
    "确认":   (0.50, 0.85),
    "取消":   (0.42, 0.85),
    "应用":   (0.58, 0.85),
    "是":     (0.45, 0.85),
    "否":     (0.55, 0.85),
    # 导航
    "桌面":   (0.02, 0.50),
    "文档":   (0.02, 0.55),
    "下载":   (0.02, 0.60),
}


class ElementLocator:
    """3级元素定位：OCR（主力） → 模板坐标 → 视觉模型（兜底）。"""

    # OCR 前将截图缩放到的最大宽度（加速识别）
    OCR_MAX_WIDTH = 1920

    def __init__(self, config: Config = None, screen_w: int = 1920, screen_h: int = 1080):
        self.config = config or Config()
        self.screen_w = screen_w
        self.screen_h = screen_h
        self._ocr = None  # 延迟初始化
        self._scale = 1.0  # OCR 缩放比例

    @property
    def ocr(self):
        """延迟加载 RapidOCR（首次调用时初始化，自动下载模型 ~30MB）。"""
        if self._ocr is None:
            from rapidocr_onnxruntime import RapidOCR
            self._ocr = RapidOCR()
        return self._ocr

    # ── 主 API ─────────────────────────────────────────────────

    def find_text(
        self,
        image: Image.Image,
        target: str,
        fallback: list[str] = None,
    ) -> Optional[tuple[int, int]]:
        """在截图中查找目标文字，返回中心坐标 (x, y)，未找到返回 None。

        查找顺序：OCR → 模板坐标估计。
        """
        # 策略1：OCR
        coord = self._ocr_find(image, target)
        if coord:
            return coord
        if fallback:
            for fb in fallback:
                coord = self._ocr_find(image, fb)
                if coord:
                    return coord

        # 策略2：模板坐标估算
        coord = self._template_estimate(target)
        if coord:
            return coord
        if fallback:
            for fb in fallback:
                coord = self._template_estimate(fb)
                if coord:
                    return coord

        return None

    def find_all(self, image: Image.Image, target: str) -> list[tuple[int, int]]:
        """查找目标文字的所有出现位置，返回坐标列表。"""
        results = self._ocr_find_all(image, target)
        return results

    def wait_for_text(
        self,
        image: Image.Image,
        target: str,
        fallback: list[str] = None,
        timeout: float = None,
    ) -> Optional[tuple[int, int]]:
        """在截图中查找目标文字（单次截图，封装为统一接口）。

        注意：轮询逻辑由 ActionExecutor 负责，这里只做单次查找。
        """
        return self.find_text(image, target, fallback)

    # ── 策略1：OCR ─────────────────────────────────────────────

    def _ocr_find(self, image: Image.Image, target: str) -> Optional[tuple[int, int]]:
        """OCR 识别截图 → 模糊匹配目标文字 → 返回中心坐标。"""
        results = self._ocr_recognize(image)
        best, best_score, best_text = None, self.config.ocr_fuzzy_threshold, ""

        for text, bbox in results:
            score = self._match_score(target, text)
            if score > best_score:
                best_score = score
                best = bbox
                best_text = text

        if best:
            x1, y1, x2, y2 = best
            y_center = (y1 + y2) // 2
            bbox_w = x2 - x1

            # 子串匹配时根据 target 在 OCR 文字中的位置偏移 x 坐标
            t_lower = target.lower()
            o_lower = best_text.lower()
            if t_lower in o_lower and len(o_lower) > len(t_lower):
                idx = o_lower.index(t_lower)
                char_w = bbox_w / len(o_lower) if len(o_lower) > 0 else bbox_w
                target_center_x = int(x1 + char_w * (idx + len(target) / 2))
            else:
                target_center_x = (x1 + x2) // 2

            coord = (target_center_x, y_center)
            if best_score < 0.9:
                print(f"[OCR] 模糊匹配 target='{target}' → ocr_text='{best_text}' score={best_score:.2f} @{coord}")
            else:
                print(f"[OCR] 匹配 target='{target}' → ocr_text='{best_text}' @{coord}")
            return coord
        return None

    def _ocr_find_all(self, image: Image.Image, target: str) -> list[tuple[int, int]]:
        """OCR 识别 → 返回所有匹配位置的坐标列表。"""
        results = self._ocr_recognize(image)
        coords = []
        for text, bbox in results:
            score = self._match_score(target, text)
            if score >= self.config.ocr_fuzzy_threshold:
                x1, y1, x2, y2 = bbox
                coords.append(((x1 + x2) // 2, (y1 + y2) // 2))
        return coords

    def _ocr_recognize(self, image: Image.Image) -> list[tuple[str, tuple[int, int, int, int]]]:
        """对 PIL Image 执行 OCR，返回 [(文字, (x1,y1,x2,y2)), ...]。
        自动缩放加速识别，坐标自动映射回原始尺寸。"""
        # 缩放加速
        w, h = image.size
        if w > self.OCR_MAX_WIDTH:
            self._scale = w / self.OCR_MAX_WIDTH
            new_w = self.OCR_MAX_WIDTH
            new_h = int(h / self._scale)
            image = image.resize((new_w, new_h), Image.LANCZOS)
        else:
            self._scale = 1.0

        img_array = np.array(image)
        result, _elapse = self.ocr(img_array)
        if not result:
            return []

        results = []
        for bbox, text, _conf in result:
            # bbox: [[x1,y1],[x2,y2],[x3,y3],[x4,y4]]
            x1 = int(min(p[0] for p in bbox) * self._scale)
            y1 = int(min(p[1] for p in bbox) * self._scale)
            x2 = int(max(p[0] for p in bbox) * self._scale)
            y2 = int(max(p[1] for p in bbox) * self._scale)
            results.append((text, (x1, y1, x2, y2)))
        return results

    # ── 模糊匹配 ───────────────────────────────────────────────

    def _match_score(self, target: str, ocr_text: str) -> float:
        """计算目标文字与 OCR 识别文字的匹配度 (0.0 ~ 1.0)。"""
        t = target.lower().replace(" ", "").replace("\n", "")
        o = ocr_text.lower().replace(" ", "").replace("\n", "")
        if t == o:
            return 1.0
        # target 是 OCR 文字的子串（如 target="东方财富", ocr_text="东方财富软件"）
        if t in o:
            return 0.9
        # 反向子串仅在 OCR 文字足够长时接受，避免 "ea" in "eastmoney" 这类误报
        if o in t and len(o) >= 3:
            return 0.85
        return difflib.SequenceMatcher(None, t, o).ratio()

    # ── 策略2：模板坐标估算 ────────────────────────────────────

    def _template_estimate(self, target: str) -> Optional[tuple[int, int]]:
        """根据常见 UI 模式推测目标的大致位置（相对坐标 × 屏幕尺寸）。"""
        pos = TEMPLATE_POSITIONS.get(target)
        if not pos:
            return None
        rx, ry = pos
        return (int(self.screen_w * rx), int(self.screen_h * ry))

    # ── 工具 ───────────────────────────────────────────────────

    def update_screen_size(self, w: int, h: int):
        """更新屏幕尺寸（用于模板坐标估算）。"""
        self.screen_w = w
        self.screen_h = h

"""全局配置"""

import datetime
from dataclasses import dataclass, field
from typing import List


@dataclass
class Config:
    """桌面 Agent 全局配置"""

    # ── 元素定位 ──
    ocr_lang: str = "ch"           # PaddleOCR 语言
    ocr_min_confidence: float = 0.5  # OCR 最低置信度
    ocr_fuzzy_threshold: float = 0.75  # 模糊匹配阈值

    # ── 小模型 ──
    ollama_base_url: str = "http://localhost:11434"
    text_model: str = "qwen3.5:4b"       # 文本推理
    vision_model: str = "qwen3.5:4b"     # 视觉定位兜底

    # ── 超时与延迟（秒） ──
    step_timeout: float = 30.0      # 单步操作最大等待
    post_action_delay: float = 0.3  # 操作后等待
    window_load_delay: float = 3.0  # 启动应用后等待
    target_appear_timeout: float = 10.0  # OCR 目标出现最大等待
    dialog_timeout: float = 10.0    # 对话框出现等待
    max_retries: int = 3            # 单步最大重试

    # ── 鼠标移动 ──
    mouse_move_step: int = 300      # "鼠标下移/上移" 单次移动的像素距离

    # ── 路径 ──
    log_dir: str = "./logs"         # 日志目录
    screenshot_dir: str = "./logs/screenshots"  # 截图目录

    @property
    def today_date(self) -> str:
        """当天日期 YYYYMMDD"""
        return datetime.date.today().strftime("%Y%m%d")

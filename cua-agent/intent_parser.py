"""意图解析器 — 自然语言 → 结构化 Intent。

两阶段解析：
    1. 关键词 + 正则匹配（快路径，80% 常见指令，<0.001s）
    2. Ollama 文本模型（慢路径，复杂/模糊指令，~1s）
"""

import re
from dataclasses import dataclass, field
from typing import Optional

from config import Config


@dataclass
class Intent:
    """解析后的结构化意图。"""
    action: str                     # launch|search|close|type|export|navigate|unknown
    app: str = ""                   # 目标应用（标准化名称）
    query: str = ""                 # 搜索关键词 / 要输入的文本
    params: dict = field(default_factory=dict)  # 额外参数


# ── 动作关键词（正则 → 动作类型）──────────────────────────────

_ACTION_RULES: list[tuple[str, str]] = [
    # (r"帮我|agent|自动操作|自动完成",     "agent"),  # 暂时弃用 agent，全部走关键词+模板
    (r"打开|open|launch|启动|运行",     "launch"),
    (r"搜索|search|查找|搜一下",         "search"),
    (r"关闭|close|退出|关掉|×掉",        "close"),
    (r"输入|type|打字|写|键入",         "type"),
    (r"导出|export|下载数据|下载|保存数据",   "export"),
    (r"点击|click|按|按下",             "click"),
    (r"导航|navigate|跳转|去",          "navigate"),
    (r"整理|organize|排列|分类",        "organize"),
    (r"截图|screenshot|截屏",           "screenshot"),
]

# 复合指令连接词（"点击A，再B" → ["A", "B"]）
_COMPOUND_SEP = re.compile(r'[，,、]\s*(?:再|然后|接着|并|以及|和|再点击|再按|再点)\s*')

# 复合片段内的动作词（用于识别"右键""鼠标下移"等，一个片段可含多个动作）
_SEGMENT_ACTIONS: list[tuple[str, str]] = [
    (r"鼠标下移|鼠标向下|下移鼠标|鼠标往下", "move_down"),
    (r"鼠标上移|鼠标向上|上移鼠标|鼠标往上", "move_up"),
    (r"右键|右击|鼠标右键",             "right_click"),
    (r"双击|鼠标双击",                 "double_click"),
    (r"悬停|hover|鼠标悬停|悬停到",      "hover"),
    (r"点击|单击|按|按下|找到|定位|寻找",  "click"),
    (r"打开|启动|运行",                 "launch"),
    (r"输入|打字|键入",                 "type"),
    (r"搜索|查找",                     "search"),
    (r"关闭|退出|关掉",                 "close"),
]


def _parse_segment(segment: str) -> list[dict]:
    """解析单个片段为动作列表。片段可含多个动作词，如"鼠标下移右键"→ move_down + right_click。"""
    segment = segment.strip().strip("，,。. ")
    if not segment:
        return []
    # 找到片段内所有动作词的区间
    matches = []
    for pattern, action in _SEGMENT_ACTIONS:
        for m in re.finditer(pattern, segment, re.IGNORECASE):
            matches.append((m.start(), m.end(), action))
    if not matches:
        return [{"action": "click", "target": segment}]
    matches.sort(key=lambda x: x[0])
    result = []
    for i, (start, end, action) in enumerate(matches):
        next_start = matches[i + 1][0] if i + 1 < len(matches) else len(segment)
        # 目标截断到第一个逗号，丢弃"，导出数据"这类冗余尾缀
        target = re.split(r"[，,、]", segment[end:next_start], maxsplit=1)[0]
        target = target.strip().strip("，,。. ")
        result.append({"action": action, "target": target})
    return result


def _parse_compound(text: str) -> list[dict]:
    """把复合指令解析为动作序列 [{action, target}, ...]。"""
    parts = _COMPOUND_SEP.split(text)
    seq = []
    for part in parts:
        part = part.strip().strip("，,。. ")
        if not part:
            continue
        seq.extend(_parse_segment(part))
    return seq

# ── 应用别名（关键词 → 标准化名称）────────────────────────────

_APP_ALIASES: dict[str, list[str]] = {
    "chrome":       ["chrome", "谷歌", "谷歌浏览器", "google", "浏览器"],
    "edge":         ["edge", "微软浏览器"],
    "notepad":      ["notepad", "记事本"],
    "file_explorer": ["文件管理器", "资源管理器", "explorer", "文件夹", "我的电脑", "此电脑"],
    "eastmoney":    ["东方财富", "eastmoney", "股票", "股票软件"],
    "calculator":   ["calculator", "计算器"],
    "word":         ["word", "文档"],
    "excel":        ["excel", "表格"],
    "vscode":       ["vscode", "vs code", "code", "编辑器"],
    "taskmgr":      ["任务管理器", "task manager"],
    "cmd":          ["cmd", "终端", "命令行", "terminal", "命令提示符"],
}


def _match_action(text: str) -> str:
    """从文本中匹配动作类型。agent 优先，其他取最后一个（最终目标）。"""
    last_action = "unknown"
    for pattern, action in _ACTION_RULES:
        if re.search(pattern, text, re.IGNORECASE):
            if action == "agent":
                return "agent"  # agent 最高优先级，立即返回
            last_action = action
    return last_action


def _split_compound_targets(text: str) -> list[str]:
    """拆分复合指令中的多个点击目标。
    "游客登录，再沪深京排行" → ["游客登录", "沪深京排行"]
    """
    parts = _COMPOUND_SEP.split(text)
    return [p.strip().strip("，,。. ") for p in parts if p.strip().strip("，,。. ")]


def _match_app(text: str) -> Optional[str]:
    """从文本中匹配目标应用。"""
    text_lower = text.lower()
    for app_name, aliases in _APP_ALIASES.items():
        for alias in aliases:
            if alias.lower() in text_lower:
                return app_name
    return None


def _extract_query(text: str, action: str) -> str:
    """从文本中提取搜索/输入的关键词。"""
    # 去掉动作词和应用名，剩下的作为 query
    s = text
    for pattern, _act in _ACTION_RULES:
        s = re.sub(pattern, "", s, flags=re.IGNORECASE)
    for aliases in _APP_ALIASES.values():
        for alias in aliases:
            s = re.sub(re.escape(alias), "", s, flags=re.IGNORECASE)
    return s.strip().strip("，,。. ")


class IntentParser:
    """意图解析器。"""

    def __init__(self, config: Config = None):
        self.config = config or Config()

    def parse(self, text: str) -> Intent:
        """解析自然语言指令 → Intent。先走快路径，失败则走模型。"""
        text = text.strip()
        if not text:
            return Intent(action="unknown")

        # 快路径：关键词 + 正则
        intent = self._fast_parse(text)
        if intent.action != "unknown" and intent.app:
            return intent

        # 慢路径：Ollama 文本模型（暂未接入时返回 best-effort）
        return self._slow_parse(text) if self._ollama_available() else intent

    def _fast_parse(self, text: str) -> Intent:
        """关键词 + 正则匹配。"""
        action = _match_action(text)
        app = _match_app(text)

        if action == "agent":
            # Agent 模式使用原始完整指令，不做关键词剥离
            query = text
        elif action in ("search", "type", "click", "navigate", "export"):
            query = _extract_query(text, action)
        else:
            query = ""

        params = {}
        if action == "click":
            # 复合指令：解析成动作序列，支持 点击/右键/双击/鼠标移动 等混合动作
            actions = _parse_compound(text)
            if len(actions) > 1:
                params["actions"] = actions
            else:
                # 单一点击，沿用原有 targets 逻辑
                targets = _split_compound_targets(query)
                if len(targets) > 1:
                    params["targets"] = targets

        return Intent(
            action=action,
            app=app or "",
            query=query,
            params=params,
        )

    def _slow_parse(self, text: str) -> Intent:
        """Ollama 文本模型兜底（约 1s）。"""
        prompt = _build_parse_prompt(text)
        try:
            import requests
            resp = requests.post(
                f"{self.config.ollama_base_url}/api/generate",
                json={
                    "model": self.config.text_model,
                    "prompt": prompt,
                    "stream": False,
                    "think": False,
                    "options": {"num_predict": 256},
                },
                timeout=self.config.step_timeout,
            )
            data = resp.json()
            return self._parse_model_output(data.get("response", ""))
        except Exception:
            return Intent(action="unknown")

    def _parse_model_output(self, output: str) -> Intent:
        """解析模型输出的 JSON → Intent。"""
        import json
        try:
            # 提取 JSON 块
            match = re.search(r"\{[^}]+\}", output)
            if match:
                obj = json.loads(match.group())
                return Intent(
                    action=obj.get("action", "unknown"),
                    app=obj.get("app", ""),
                    query=obj.get("query", ""),
                    params=obj.get("params", {}),
                )
        except (json.JSONDecodeError, KeyError):
            pass
        return Intent(action="unknown")

    def _ollama_available(self) -> bool:
        """检查 Ollama 服务是否可用。"""
        try:
            import requests
            resp = requests.get(f"{self.config.ollama_base_url}/api/tags", timeout=2)
            return resp.status_code == 200
        except Exception:
            return False


def _build_parse_prompt(user_text: str) -> str:
    """构建发给文本模型的解析提示词。"""
    return f"""你是一个桌面助手意图解析器。将用户指令解析为 JSON。

动作类型: launch(打开应用), search(搜索), close(关闭), type(输入), export(导出数据), click(点击), navigate(导航), unknown(未知)

应用列表: chrome, edge, notepad, file_explorer, eastmoney, calculator, word, excel, vscode, taskmgr, cmd

输出格式: {{"action": "动作", "app": "应用", "query": "搜索词或文本"}}

示例:
"打开Chrome搜索Python教程" → {{"action": "search", "app": "chrome", "query": "Python教程"}}
"导出东方财富沪深A股数据" → {{"action": "export", "app": "eastmoney", "query": "沪深A股"}}
"帮我打开记事本写一段话" → {{"action": "launch", "app": "notepad"}}

用户指令: {user_text}
JSON:"""

"""任务规划器 — Intent → Step 序列。

策略:
    1. 模板库匹配（优先）——根据 intent.app 找到对应模板，根据 intent.action 找到对应 skill
    2. Ollama 文本模型推理（兜底）——未知应用时让模型自己规划步骤
"""

import importlib
import os
import pkgutil
from dataclasses import dataclass, field
from typing import Optional

from action_executor import Step
from config import Config
from intent_parser import Intent


@dataclass
class AppTemplate:
    """单个应用的模板。"""
    name: str                       # 标准化名称
    aliases: list[str]              # 用户可能用的别称
    launch_name: str = ""           # 启动时在开始菜单搜索的名称
    window_keywords: list[str] = field(default_factory=list)  # 窗口标题关键词
    skills: list[dict] = field(default_factory=list)           # 预置技能列表


class TaskPlanner:
    """任务规划器。加载模板库，匹配 Intent → 生成 Step 序列。"""

    def __init__(self, config: Config = None):
        self.config = config or Config()
        self._templates: dict[str, AppTemplate] = {}  # app_name → template
        self._load_templates()

    # ── 模板加载 ───────────────────────────────────────────────

    def _load_templates(self):
        """扫描 skill_library/ 目录，加载所有 .py 模板文件。"""
        lib_path = os.path.join(os.path.dirname(__file__), "skill_library")
        if not os.path.isdir(lib_path):
            os.makedirs(lib_path, exist_ok=True)
            # 创建 __init__.py
            init_path = os.path.join(lib_path, "__init__.py")
            if not os.path.exists(init_path):
                with open(init_path, "w", encoding="utf-8") as f:
                    f.write("# Skill template library\n")
            return

        for _finder, name, _ispkg in pkgutil.iter_modules([lib_path]):
            if name.startswith("_"):
                continue
            try:
                mod = importlib.import_module(f"skill_library.{name}")
                if hasattr(mod, "TEMPLATE"):
                    tmpl_data = mod.TEMPLATE
                    app = tmpl_data.get("app", {})
                    template = AppTemplate(
                        name=app.get("name", name),
                        aliases=app.get("aliases", []),
                        launch_name=app.get("launch_name", app.get("name", name)),
                        window_keywords=app.get("window", {}).get("title_keywords", app.get("aliases", [])),
                        skills=tmpl_data.get("skills", []),
                    )
                    self._templates[template.name] = template
                    for alias in template.aliases:
                        self._templates[alias] = template
            except Exception as e:
                print(f"[TaskPlanner] 加载模板 {name} 失败: {e}")

    # ── 主 API ─────────────────────────────────────────────────

    def plan(self, intent: Intent) -> tuple[list[Step], list[str]]:
        """根据意图生成步骤序列。返回 (steps, window_keywords)。"""
        app = intent.app

        # 策略1：模板匹配
        template = self._match_template(app)
        if template:
            steps = self._match_skill(template, intent)
            if steps:
                # 需要先打开应用的操作类型，自动插入 launch
                if intent.action in ("search", "export", "type", "navigate", "click"):
                    steps = self._prepend_launch(template, steps)
                return steps, template.window_keywords
            # 模板匹配但 skill 不匹配：生成通用步骤，但保留模板的窗口关键词
            steps = self._generic_steps(intent, template)
            return steps, template.window_keywords

        # 策略2：Ollama 推理（未接入时返回通用 launch 步骤）
        return self._fallback_plan(intent), []

    def _match_template(self, app_name: str) -> Optional[AppTemplate]:
        """匹配模板：先精确匹配 name，再匹配 aliases。"""
        if not app_name:
            return None
        return self._templates.get(app_name)

    def _match_skill(self, template: AppTemplate, intent: Intent) -> list[Step]:
        """在模板中匹配 intent.action → skill.triggers。"""
        for skill in template.skills:
            triggers = skill.get("triggers", [])
            for trigger in triggers:
                if trigger.lower() == intent.action.lower():
                    return self._build_steps(skill.get("steps", []), intent)
        return []

    def _build_steps(self, step_dicts: list[dict], intent: Intent) -> list[Step]:
        """将模板中的 dict 列表转为 Step 对象列表，填充参数。"""
        steps = []
        for sd in step_dicts:
            text = sd.get("text", "")
            # 变量替换
            if text and "$" in text:
                text = text.replace("$query", intent.query or "")
                text = text.replace("$app", intent.app or "")
                text = text.replace("$section", intent.params.get("section", ""))
                text = text.replace("$date", self.config.today_date)

            target = sd.get("target", "")
            if target and "$" in target:
                target = target.replace("$query", intent.query or "")
                target = target.replace("$section", intent.params.get("section", ""))

            fallback = sd.get("fallback")
            if fallback:
                fallback = [
                    fb.replace("$section", intent.params.get("section", ""))
                    if "$" in (fb or "") else fb
                    for fb in fallback
                ]

            steps.append(Step(
                type=sd.get("type", "wait"),
                target=target or None,
                text=text or None,
                keys=sd.get("keys"),
                key=sd.get("key"),
                seconds=sd.get("seconds"),
                fallback=fallback,
                optional=sd.get("optional", False),
                repeat=sd.get("repeat", 1),
            ))
        return steps

    def _prepend_launch(self, template: AppTemplate, steps: list[Step]) -> list[Step]:
        """在操作步骤前插入 launch 步骤（如果模板中有 launch skill）。"""
        for skill in template.skills:
            if skill.get("name") == "launch":
                launch_steps = self._build_steps(skill.get("steps", []), Intent(action="launch", app=template.name))
                # 标记 launch 为 optional（窗口可能已打开）
                for s in launch_steps:
                    s.optional = True
                return launch_steps + steps
        # 没有 launch skill，生成通用 launch
        launch_step = Step(
            type="launch",
            text=template.launch_name,
            optional=True,
        )
        return [launch_step] + steps

    def _generic_steps(self, intent: Intent, template: AppTemplate) -> list[Step]:
        """模板匹配但无对应 skill 时，根据 intent 生成通用步骤。"""
        steps = []
        action = intent.action
        query = intent.query
        targets = intent.params.get("targets", [])

        if action == "click" and targets:
            for t in targets:
                steps.append(Step(type="click", target=t))
        elif action == "click" and query:
            steps.append(Step(type="click", target=query))
        elif action == "type" and query:
            steps.append(Step(type="type", text=query))
        elif action == "search" and query:
            steps.append(Step(type="click", target="搜索框",
                             fallback=["搜索", "地址栏"]))
            steps.append(Step(type="type", text=query))
            steps.append(Step(type="press", key="enter"))
        elif action == "navigate" and query:
            steps.append(Step(type="click", target=query))
        else:
            steps.append(Step(type="wait", seconds=0.5))

        return self._prepend_launch(template, steps)

    def _fallback_plan(self, intent: Intent) -> list[Step]:
        """无模板时的通用兜底计划。"""
        steps = []
        if intent.app:
            steps.append(Step(
                type="launch",
                text=intent.app,
                optional=True,
            ))
        steps.append(Step(type="wait", seconds=1.0))
        return steps

    # ── 已知应用列表（供主界面使用）────────────────────────────

    def list_apps(self) -> list[str]:
        """返回所有已注册的应用名称。"""
        seen = set()
        apps = []
        for tmpl in self._templates.values():
            if tmpl.name not in seen:
                seen.add(tmpl.name)
                apps.append(tmpl.name)
        return sorted(apps)

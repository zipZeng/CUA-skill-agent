# CUA-Skill Agent

面向 Windows 桌面环境的 AI 自动化操作 Agent（#25 实训项目）。用户用自然语言下达指令，系统自动操作桌面 GUI 完成任务。

## 架构

```
用户自然语言指令
        │
        ▼
┌──────────────────────────────┐
│  skill_matcher.py  技能匹配器 │  ← 正则快路径 + 评分慢路径，零 Token
├──────────────────────────────┤
│  agent_rag.py  执行引擎      │  ← 按预定义模板逐步执行，UIA 定位坐标
├──────────────────────────────┤
│  mixture_grounding.py        │  ← Windows UIA（主）+ Ollama 视觉（兜底）
└──────────────────────────────┘
        │
        ▼
  desktop_env.step(gui_code)    → pyautogui / pywinauto 执行
```

## 环境要求

- Windows 10/11
- Python 3.10+
- [Ollama](https://ollama.com/) 已安装并运行
- 视觉模型：`ollama pull qwen2.5vl:7b`（约 4.5GB，需 8G+ VRAM）

## 快速开始

```bash
# 安装依赖
cd cua_skill
pip install -r agent/requirements.txt
pip install flask

# 确保 Ollama 在运行
ollama serve

# CLI 方式执行
python run.py "Open Notepad"
python run.py -c agent/config_ollama.json "打开计算器"

# 直接模式（绕过 AI，更快）
python run_direct.py "Open Word"

# Web 控制台（推荐）
python web/app.py
# 浏览器打开 http://localhost:5000

# 技能匹配测试
python test_match.py
```

## 项目结构

| 路径 | 说明 |
|------|------|
| `agent/skill_matcher.py` | **新增**。指令→技能匹配器，正则 + 关键词评分 |
| `agent/agent_rag.py` | **重写**。执行引擎，匹配技能后按固定模板执行 |
| `agent/mixture_grounding.py` | **修改**。UIA 坐标定位 + Ollama 视觉兜底 |
| `agent/config_ollama.json` | **新增**。Ollama 本地模型专用配置 |
| `agent/action/` | 预置 252 个组合动作（Notepad/Word/Excel/Chrome 等） |
| `web/app.py` | **新增**。Flask Web 控制台后端 |
| `web/templates/index.html` | **新增**。Web 控制台前端页面 |
| `run.py` | **新增**。CLI 主入口 |
| `run_direct.py` | **新增**。绕过 AI 直接执行 |
| `test_match.py` | **新增**。技能匹配器单元测试（29 用例） |
| `test_quick.py` | **新增**。组件诊断测试（Ollama / pyautogui / Planner） |
| `change.md` | **新增**。完整改动记录 |
| `detail.md` | **新增**。项目流程文档 |

## 支持的指令类型

| 指令类型 | 示例 |
|---------|------|
| 打开应用 | `open Word`, `打开记事本`, `帮我打开excel` |
| 关闭应用 | `close notepad`, `关闭记事本` |
| 输入文字 | `type hello in notepad`, `输入test in word` |
| 保存文件 | `save file in notepad`, `save as doc in word` |
| 缩放 | `zoom in notepad`, `zoom out chrome` |
| 搜索 | `search python in chrome` |
| 查找替换 | `find hello and replace with world in notepad` |
| 复制 | `copy item in file explorer` |

## 两种执行模式

| 模式 | 命令 | 说明 |
|------|------|------|
| Agent 模式 | `python run.py "open word"` | 技能匹配 → 模板执行 → UIA 定位 |
| 直接模式 | `python run_direct.py "open word"` | Win + 输入 + Enter，绕过所有 AI |

## 性能

| 环节 | 方式 | 耗时 |
|------|------|------|
| 指令→技能匹配 | 正则 + 关键词 | < 0.001s |
| 技能步骤执行 | 预定义固定模板 | 取决于操作数量 |
| 点击坐标定位 | Windows UIA API | < 0.01s |
| LLM 视觉定位 | Ollama（仅兜底） | ~10s |

## 项目状态

- ✅ 技能匹配器（29/29 测试通过）
- ✅ Agent 执行引擎（无 LLM 推理）
- ✅ UIA 坐标定位（像素级）
- ✅ Web 控制台
- ✅ Ollama 本地模型适配
- ✅ 直接执行模式
- ⏳ 定时调度机制
- ⏳ 自定义 Skill 封装
- ⏳ WindowsAgentArena 基准评估

## 框架来源

基于 [microsoft/cua_skill](https://github.com/microsoft/cua_skill) 框架修改，MIT License。

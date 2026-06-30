# 项目 #25：CUA Skill（小龙虾）

## 项目定义

用 AI 驱动代替人手操作桌面软件——打开程序、点菜单、下载数据、发邮件等重复性劳动自动化。

## 三层架构（自底向上）

| 层级 | 是什么 | 在这个项目里 |
|------|--------|-------------|
| **大模型** | 基础底座，看图理解、规划决策 | Ollama + qwen2.5vl-vision（本地，零 Token 费） |
| **Agent** | 专用领域模型，理解任务并分派给 Skill | CUA Skill 框架（微软开源） |
| **Skill** | 固定的操作流程，执行具体动作（点击、键入等） | `agent/action/` 目录下的技能模块 |

## 两个版本

| 版本 | 方案 | 优势 | 当前状态 |
|------|------|------|----------|
| **API 版** | 云端视觉大模型（GPT-4o / GLM 5.2 / Kimi CLI） | 精度高 | 待做 |
| **本地版** | Ollama + qwen2.5vl-vision（7B ~4.7G） | 零 Token 费 | 进行中 |

## 三个阶段

| 阶段 | 目标 | 当前进度 |
|------|------|----------|
| **一** | 下载 CUA Skill 框架 → 搭起来 → 跑通 → 能接收自然语言指令打开某软件 | 进行中（框架已跑通，能选动作，坐标定位待优化） |
| **二** | 老师提供实际用例（如每天定时用某软件下载 N 个文档），实现具体操作 | 待老师演示 |
| **三** | 自己训练一个定制 Skill，比开源 Skill 更好用、更快 | 待做 |

## 技术栈

- **框架**: CUA Skill（微软开源，基于 Python）
- **Agent 模式**: RAG Agent（动态规划模式）
- **本地大模型**: qwen2.5vl-vision（Qwen2.5-VL 7B + CLIP mmproj）
- **桌面操控**: pyautogui + pywinauto
- **视觉定位**: Ollama VL 模型（替代 UI-TARS）
- **运行环境**: Windows + RTX 3060 8G 显存

## 项目路径

- 代码目录: `D:\Project\cua-skill\cua_skill`
- 配置文件: `agent/config_ollama.json`
- 入口脚本: `run.py`
- 改动记录: `change.md`
- 模型文件: `D:\env\ollama\models`
- Ollama 模型名: `qwen2.5vl-vision`

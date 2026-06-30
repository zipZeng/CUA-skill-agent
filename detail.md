# CUA-Skill：面向桌面环境的计算机使用 Agent 技能库

> **项目编号**：#25 | **类别**：大模型 | **建议语言**：Python + Rust | **团队规模**：4 人
> **一句话**：用 AI 驱动鼠标键盘，代替人手完成 Windows 桌面上的重复性操作（打开软件、点击菜单、下载数据、编辑文档等）。

---

## 一、项目定义

### 这是什么

一个 **三层 AI 桌面自动化系统**：用户用自然语言下达指令（如"每天下午三点打开 XX 软件，从菜单下载数据到 D 盘"），系统自动操作桌面 GUI 完成任务。

```
用户自然语言指令
        │
        ▼
   ┌─────────────┐
   │   Skills    │  ← 技能层：预定义的固定操作流程（打开软件、点击菜单、输入文字...）
   ├─────────────┤
   │   Agent     │  ← 代理层：理解指令 → 匹配合适技能 → 调度执行
   ├─────────────┤
   │   大模型     │  ← 模型层：Ollama 本地 / API 云端，负责识图和坐标定位
   └─────────────┘
        │
        ▼
   桌面 GUI 操作（鼠标点击、键盘输入、窗口切换...）
```

### 核心价值

- **替代重复性人工操作**：每天点 50 次鼠标的重复劳动 → 一句话自动完成
- **本地模型零 Token 消耗**：日常操作不走云端，不花钱
- **技能可复用、可组合、可自定义**：一次编写，永久使用

---

## 二、老师的要求（⭐ 核心目标）

### 总体要求

| 项目 | 说明 |
|---|---|
| **两个版本** | API 版（接 GPT-4o / Claude）+ 本地版（Ollama + qwen2.5vl:7b） |
| **核心能力** | 输入自然语言指令，系统自动操作桌面 GUI 完成任务 |
| **两周交付** | 能做多少做多少，不要求大而全 |

### 三阶段路线

```
阶段 1 ─────────────── 阶段 2 ─────────────── 阶段 3
搭框架，跑通           实现老师的具体用例        自己训练一个 Skill
"打开 Word" 能成功     定时下载数据             比下载的更好用
```

#### 阶段 1：搭框架（已完成 ✅）

- 下载 CUA-Skill 开源框架，配通
- 输入"打开某某软件"，系统能自动打开
- API 版 + 本地 Ollama 版都能跑

#### 阶段 2：实现老师的具体用例（当前任务 ⏳）

老师的原话：
> "给你们一个实例：每天下午三点半，打开某个软件，从某某菜单点击右键选择什么，然后点下载，存到硬盘某个目录，然后再点另外的菜单，右下载什么数据到另外一个文件夹。定时可以定义的。很简单，就是给他一个语言指令就行了。"

**关键要素**：
- 定时触发（每天固定时间）
- 多步操作序列（打开软件 → 点击菜单 → 选择选项 → 下载 → 保存到指定路径）
- 可能涉及多个软件和多次下载

#### 阶段 3：自己训练一个 Skill（待开始）

- 把阶段 2 的操作流程固化成一个自定义 Skill
- 比开源 Skill 更准、更快

---

## 三、当前实现

### 架构（2026-06-30）

**核心决策：不用 LLM 看图推理。** 7B 模型不够聪明，改为：关键词匹配技能 → 固定模板执行 → UIA 精准定位坐标。

```
用户指令 "open Word"
    │
    ▼
┌──────────────────────────────────────┐
│  skill_matcher.py  技能匹配器         │
│                                      │
│  快路径（正则）：                      │
│    "open X"      → XLaunch           │
│    "打开 X"      → XLaunch           │
│    "type X in Y" → YTypeText         │
│    "close X"     → XExitApp          │
│    "save X"      → XSaveFile         │
│    "zoom in/out" → XZoomIn/Out       │
│                                      │
│  慢路径（评分）：                      │
│    域名加权 + 动词同义词 + 词边界匹配    │
└──────────────────────────────────────┘
    │ 返回：技能类 + 提取的参数
    ▼
┌──────────────────────────────────────┐
│  agent_rag.py  执行引擎               │
│                                      │
│  _execute_skill(skill_class, params)  │
│    ├── 实例化技能                     │
│    ├── 按固定模板逐步执行              │
│    │    step 1: HotKeyAction("win")   │
│    │    step 2: TypeAction(app_name)  │
│    │    step 3: ClickAction (UIA定位) │
│    └── 每步点击自动走 UIA 获取坐标     │
│                                      │
│  _execute_direct_fallback()          │
│    └── run_direct.py 模式兜底         │
└──────────────────────────────────────┘
    │
    ▼
┌──────────────────────────────────────┐
│  mixture_grounding.py  坐标定位       │
│                                      │
│  优先级：                             │
│    1. UIA（Windows 无障碍 API）       │
│       → 像素级精准，<0.01 秒          │
│    2. Ollama 视觉定位（兜底）          │
│       → 仅 UIA 找不到时触发           │
└──────────────────────────────────────┘
    │
    ▼
  desktop_env.step(gui_code)
    → pyautogui / pywinauto 执行实际鼠标键盘操作
```

### 关键文件

| 文件 | 作用 |
|---|---|
| `agent/skill_matcher.py` | **新增**。指令→技能匹配，正则快路径 + 评分慢路径，零 Token |
| `agent/agent_rag.py` | **重写**。执行引擎，匹配技能后按固定模板执行，不再 LLM 每步推理 |
| `agent/mixture_grounding.py` | UIA 坐标定位 + Ollama 视觉定位兜底 |
| `agent/action/base_action.py` | 基础动作定义（单击、双击、输入、热键等 60+ 动作类） |
| `agent/action/compose_action.py` | 组合动作基类（有向图执行引擎） |
| `agent/action/common_action.py` | 通用技能（LaunchApplication、OpenWindowsMenu） |
| `agent/action/notepad_action.py` | 记事本技能（30+：启动、输入、查找替换、保存...） |
| `agent/action/word_action.py` | Word 技能（30+） |
| `agent/action/excel_action.py` | Excel 技能（20+） |
| `agent/action/chrome_actions.py` | Chrome 技能（25+） |
| `agent/action/file_explorer_action.py` | 文件管理器技能（30+） |
| `agent/action/calculator_action.py` | 计算器技能（25+） |
| `agent/utils/_uia.py` | Windows UIA 底层封装 |
| `agent/desktop_env.py` | 桌面环境抽象层 |
| `run_direct.py` | **新增**。绕过所有 AI，直接 Win+输入执行 |
| `run.py` | 主入口 |

### 预置技能统计（252 个）

| 类别 | 数量 | 示例 |
|---|---|---|
| 通用 | 6 | LaunchApplication, OpenWindowsMenu, OpenRun... |
| 记事本 | 33 | NotepadLaunch, NotepadTypeText, NotepadFindReplaceAll, NotepadSaveAs... |
| Word | 41 | WordLaunch, WordInsertText, WordSaveAs, WordExportPDF... |
| Excel | 20 | ExcelLaunch, ExcelSetCellValue, ExcelAutoSum, ExcelDrawChart... |
| PowerPoint | 36 | PowerPointLaunch, PowerPointInsertText, PowerPointAddSlide... |
| Chrome | 29 | ChromeLaunch, ChromeOpenURL, ChromeSearchWeb, ChromeDownloadFile... |
| Edge | 35 | MicrosoftEdgeLaunch, MicrosoftEdgeNewSearchQuery... |
| Bing | 20 | BingSearchQuery, BingOpenResult, BingSearchVoice... |
| 文件管理器 | 32 | FileExplorerLaunch, FileExplorerCopyItem, FileExplorerSearchItem... |
| 计算器 | 27 | CalculatorLaunch, CalculatorAdd, CalculatorSquareRoot... |
| VSCode | 21 | VSCodeLaunch, VSCodeOpenFile, VSCodeRunCommand... |
| Windows 设置 | 22 | WindowsSettingsOpenApp, WindowsSettingsToggleSwitch... |
| 其他 | VLC(28), Clock(18), YouTube(25), Amazon(20), Paint | |

### 两种运行方式

```bash
# 方式 1：完整 Agent（技能匹配 + 固定模板执行）
python run.py -c agent/config_ollama.json "Open Word"

# 方式 2：直接执行（绕过所有 AI，纯按键模拟）
python run_direct.py "Open Word"
```

### 不依赖 LLM 的环节

| 环节 | 方式 | 耗时 |
|---|---|---|
| 指令→技能匹配 | 正则 + 关键词 | < 0.001s |
| 技能步骤执行 | 预定义固定模板 | 取决于操作数量 |
| 点击坐标定位 | UIA（Windows API） | < 0.01s |
| 键盘输入 | pyautogui | 实时 |

### LLM 仅用于兜底

- Ollama 视觉定位：仅当 UIA 找不到目标元素时触发（极少发生）
- 当前流程中 LLM 基本不参与

---

## 四、拓展目标（来自项目申报书）

以下内容来自正式项目文档，作为能力拓展方向，**非老师硬性要求**：

| 拓展项 | 说明 | 优先级 |
|---|---|---|
| MCP 协议 + ZPIT-desktop-MCP | Rust 实现的高性能桌面控制服务器，替代 pyautogui | 低 |
| OpenTelemetry + Jaeger | Agent 执行链路追踪和可视化 | 低 |
| Web 控制台 | 可视化任务监控界面 | 低 |
| Docker Compose | 一键部署 | 低 |
| WindowsAgentArena 评估 | 标准化基准测试，目标成功率 ≥55% | 低 |
| 故障恢复机制 | 执行失败自动回滚/重试/降级 | 中 |
| 记忆模块 | SQLite 跨会话任务状态保持 | 中 |
| RAG 语义检索 | 基于向量嵌入的技能动态检索（当前用关键词代替） | 中 |

---

## 五、考核文档要求

见 `D:\Project\shixun2\hulue\考核要求.md`，共需提交 **20+ 份文档**，包括：

- 任务书（含签名页）
- 项目提案、需求规格说明书（≥20 页）
- 接口设计说明书（≥10 页）
- 系统设计文档（≥10 页）、技术规范文档（≥10 页）
- 用户手册、测试计划/报告、部署计划/报告
- 项目总结报告（≥10 页）、维护手册
- **所有源代码（最重要评分依据）** + 中文注释
- 每人：工作列表 + 个人感受启发

---

## 六、当前状态与下一步

### 已完成

- [x] CUA-Skill 框架搭好，API 版 + Ollama 本地版都能跑
- [x] UIA 坐标定位（像素级精准）
- [x] 技能匹配器（skill_matcher.py，零 Token）
- [x] 直接执行模式（run_direct.py）
- [x] 常见指令可用：open/close/type/zoom/save + 应用名

### 阻塞项

- [ ] **老师的具体用例未拿到**（等待老师演示操作流程）
- [ ] 无定时调度机制

### 待开始

- [ ] 实现老师的具体用例（拿到用例后 1-2 天）
- [ ] 添加定时调度（Windows Task Scheduler / Python schedule）
- [ ] 将用例流程固化为自定义 Skill
- [ ] 补考核文档（代码完成后集中写）

# CUA-Skill 桌面 Agent

自然语言驱动的桌面自动化助手。输入指令，Agent 自动识别意图、规划步骤、操控桌面应用完成任务。

## 功能特性

- **意图解析** — 自然语言 → 结构化意图，支持中英文混合指令、复合指令拆分
- **任务规划** — 模板库匹配 + 通用步骤生成，支持扩展自定义应用
- **非独占式操控** — 激活窗口 → 执行操作 → 释放焦点，不影响用户正常工作
- **OCR 精确定位** — 截图 → 文字识别 → 子串偏移坐标计算，无需依赖 UI Automation
- **桌面图标启动** — 显示桌面 → OCR 扫描图标 → 最佳匹配双击启动（开始菜单兜底）
- **轮询等待** — 点击目标未出现时自动轮询截图等待（0.5s 间隔，最长 10s）
- **可视化界面** — Tkinter GUI，实时日志、步骤追踪、进度展示

## 架构

```
main.py              GUI 入口，用户指令 → 执行调度
intent_parser.py     意图解析（关键词正则 + 复合指令拆分 + Ollama 模型兜底）
task_planner.py      任务规划（模板库匹配 → Step 序列 / 通用步骤生成）
action_executor.py   动作执行（逐步执行，轮询等待 + 日志 + 可选步骤跳过）
window_manager.py    窗口管理（查找/激活/启动/可见点击/键鼠操作）
element_locator.py   元素定位（OCR 主力 → 模板坐标 → 视觉模型兜底）
skill_library/       应用模板库（可扩展）
```

## 环境要求

- Windows 10/11
- Python 3.10+
- [Ollama](https://ollama.com)（可选，用于复杂指令的模型推理）

## 安装

```bash
cd cua-agent
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

首次运行时会自动下载 RapidOCR 模型（约 30MB）。

## 使用

```bash
venv\Scripts\python.exe main.py
```

在 GUI 输入框中输入指令，例如：

| 指令 | 效果 |
|------|------|
| `打开东方财富` | 启动东方财富股票软件 |
| `打开东方财富，点击游客登录` | 启动 → 点击"游客登录" |
| `打开东方财富，点击游客登录，再点击沪深京排行` | 启动 → 登录 → 切换到沪深京排行 |
| `导出东方财富沪深A股数据` | 启动 → 右键板块 → 数据导出 |
| `打开Chrome搜索天气` | 启动 Chrome → 搜索"天气" |

### 复合指令

支持用 `，再`、`，然后`、`，接着` 连接多个连续操作：

```
打开东方财富，点击游客登录，再点击沪深京排行
→ [launch("东方财富"), click("游客登录"), click("沪深京排行")]
```

### OCR 定位精度

- **精确匹配** (score=1.0)：目标文字完全匹配 OCR 文字
- **子串匹配** (score=0.9)：目标文字是 OCR 文字的子串（如 target="沪深京排行" 匹配 OCR 文字 "沪深京排行·科创板·"）
- **子串偏移**：子串匹配时自动计算目标在 OCR 文字中的字符位置偏移，点击精确坐标而非整个文字块中心
- **模糊匹配** (score=0.75+)：允许 OCR 单字识别误差

## 扩展应用

在 `skill_library/` 目录下新建 `.py` 文件，参考 `_template.py`：

```python
TEMPLATE = {
    "app": {
        "name": "my_app",                    # 标准化名称
        "aliases": ["我的应用", "myapp"],      # 用户可用的别称
        "launch_name": "MyApp",              # 开始菜单搜索名
        "window": {
            "title_keywords": ["MyApp", "我的应用"],  # 窗口标题关键词
        },
    },
    "skills": [
        {
            "name": "launch",
            "triggers": ["launch", "打开", "启动"],
            "steps": [
                {"type": "launch", "text": "MyApp"},
            ],
        },
        {
            "name": "my_action",
            "triggers": ["click"],            # 匹配 intent.action
            "steps": [
                {"type": "click", "target": "目标按钮"},
            ],
        },
    ],
}
```

重启应用即可生效。

### 步骤类型

| type | 说明 | 关键字段 |
|------|------|----------|
| `launch` | 启动应用（桌面OCR → 开始菜单兜底） | `text` |
| `click` | OCR 定位 → 可见移动 → 左键点击 | `target`, `fallback` |
| `right_click` | OCR 定位 → 可见移动 → 右键点击 | `target`, `fallback` |
| `double_click` | OCR 定位 → 可见移动 → 双击 | `target`, `fallback` |
| `type` | 输入文字（剪贴板粘贴，绕过中文输入法） | `text` |
| `hotkey` | 组合键 | `keys` 如 `["ctrl", "a"]` |
| `press` | 单键 | `key` 如 `"enter"` |
| `wait` | 等待 | `seconds` |
| `scroll` | 滚动 | `text`（行数，负数为向下） |

变量支持：`$query`, `$app`, `$section`, `$date`

## 配置

编辑 `config.py` 调整参数：

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `ocr_fuzzy_threshold` | 0.75 | OCR 模糊匹配阈值 |
| `target_appear_timeout` | 10.0 | OCR 目标出现最大等待秒数 |
| `window_load_delay` | 3.0 | 应用启动后等待秒数 |
| `step_timeout` | 30.0 | 单步操作最大等待秒数 |
| `max_retries` | 3 | 单步最大重试次数 |

## 已注册应用

- **东方财富** (eastmoney) — 股票数据导出
- **Chrome** (browser) — 网页搜索
- **记事本** (notepad) — 文本编辑
- **文件管理器** (file_explorer) — 文件浏览

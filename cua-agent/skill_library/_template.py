"""空白模板 + 编写说明。

复制此文件 → 重命名为 your_app.py → 填写 app 和 skills → 重启应用即可使用。

字段说明:
    app.name:            标准化名称（英文小写，不含空格）
    app.aliases:         用户可能说的别称列表（中文、英文等）
    app.launch_name:     开始菜单搜索名（Win键 → 输入此名 → Enter 启动）
    app.window.title_keywords: 窗口标题关键词（用于自动定位窗口）

    skills[].name:       技能名称
    skills[].triggers:   触发词列表（匹配 intent.action）
    skills[].steps[]:    操作步骤

步骤类型 (step.type):
    launch      - 启动应用（Win键 → 输入 → Enter）
    click       - OCR 定位 target 文字 → 鼠标左键点击
    right_click - OCR 定位 → 右键点击
    double_click - OCR 定位 → 双击
    type        - 输入 text 内容（剪贴板粘贴）
    hotkey      - 组合键（如 ["ctrl", "a"]）
    press       - 单键（如 "enter"）
    wait        - 等待 seconds 秒
    scroll      - 滚动 text 行（负数向下）

步骤字段:
    target:   OCR 查找的目标文字
    text:     输入内容（支持变量: $query, $app, $section, $date）
    keys:     组合键列表
    key:      单键名
    seconds:  等待秒数
    fallback: 备选目标文字列表（target 未找到时依次尝试）
    optional: True 表示失败跳过继续（用于可选操作如关闭弹窗）
    repeat:   重复次数（默认 1）
"""

TEMPLATE = {
    "app": {
        "name": "example",
        "aliases": ["示例", "example"],
        "launch_name": "example",
        "window": {
            "title_keywords": ["example", "示例"],
        },
    },
    "skills": [
        {
            "name": "launch",
            "triggers": ["launch", "打开", "启动"],
            "steps": [
                {"type": "launch", "text": "$app"},
            ],
        },
        {
            "name": "example_action",
            "triggers": ["click"],
            "steps": [
                {"type": "click", "target": "目标按钮",
                 "fallback": ["备选文字"], "optional": False},
            ],
        },
    ],
}

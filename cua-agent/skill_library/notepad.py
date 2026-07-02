"""记事本模板。"""

TEMPLATE = {
    "app": {
        "name": "notepad",
        "aliases": ["notepad", "记事本", "笔记本"],
        "launch_name": "记事本",
        "window": {
            "title_keywords": ["记事本", "Notepad", "无标题"],
        },
    },
    "skills": [
        {
            "name": "launch",
            "triggers": ["launch", "打开", "启动"],
            "steps": [
                {"type": "launch", "text": "记事本"},
            ],
        },
        {
            "name": "type",
            "triggers": ["type", "输入", "写"],
            "steps": [
                {"type": "type", "text": "$query"},
            ],
        },
        {
            "name": "close",
            "triggers": ["close", "关闭", "退出"],
            "steps": [
                {"type": "hotkey", "keys": ["alt", "f4"]},
            ],
        },
    ],
}

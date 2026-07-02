"""文件资源管理器模板。"""

TEMPLATE = {
    "app": {
        "name": "file_explorer",
        "aliases": ["文件管理器", "资源管理器", "explorer", "文件夹",
                     "我的电脑", "此电脑"],
        "launch_name": "文件资源管理器",
        "window": {
            "title_keywords": ["文件资源管理器", "资源管理器", "此电脑",
                               "Windows", "Explorer"],
        },
    },
    "skills": [
        {
            "name": "launch",
            "triggers": ["launch", "打开", "启动"],
            "steps": [
                {"type": "launch", "text": "文件资源管理器"},
            ],
        },
        {
            "name": "navigate",
            "triggers": ["navigate", "导航", "跳转", "去"],
            "steps": [
                {"type": "click", "target": "地址栏",
                 "fallback": ["搜索", "路径"]},
                {"type": "wait", "seconds": 0.2},
                {"type": "hotkey", "keys": ["ctrl", "a"]},
                {"type": "type", "text": "$query"},
                {"type": "press", "key": "enter"},
                {"type": "wait", "seconds": 1.0},
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

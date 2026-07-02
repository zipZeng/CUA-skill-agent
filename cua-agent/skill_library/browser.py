"""Chrome / Edge 浏览器模板。"""

TEMPLATE = {
    "app": {
        "name": "chrome",
        "aliases": ["chrome", "谷歌", "谷歌浏览器", "google", "浏览器", "edge"],
        "launch_name": "chrome",
        "window": {
            "title_keywords": ["chrome", "谷歌", "Google", "浏览器", "Edge"],
        },
    },
    "skills": [
        {
            "name": "launch",
            "triggers": ["launch", "打开", "启动"],
            "steps": [
                {"type": "launch", "text": "chrome"},
            ],
        },
        {
            "name": "search",
            "triggers": ["search", "搜索"],
            "steps": [
                {"type": "click", "target": "地址栏",
                 "fallback": ["搜索", "网址", "chrome"]},
                {"type": "wait", "seconds": 0.2},
                {"type": "hotkey", "keys": ["ctrl", "a"]},
                {"type": "wait", "seconds": 0.1},
                {"type": "type", "text": "$query"},
                {"type": "wait", "seconds": 0.2},
                {"type": "press", "key": "enter"},
                {"type": "wait", "seconds": 2.0},
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

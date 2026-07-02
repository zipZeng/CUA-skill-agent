"""东方财富股票软件模板 — 数据导出。

板块列表（待确认）:
    沪深A股、板块数据、行业板块、概念板块、地域板块、风格板块、指数板块

导出步骤:
    1. 关闭弹窗广告
    2. 右键板块名
    3. 点击"数据导出"
    4. 在弹出的导出对话框中操作
    5. 等待文件生成
"""

TEMPLATE = {
    "app": {
        "name": "eastmoney",
        "aliases": ["东方财富", "eastmoney", "股票", "股票软件"],
        "launch_name": "东方财富",
        "window": {
            "title_keywords": ["东方财富", "eastmoney"],
        },
    },
    "skills": [
        {
            "name": "launch",
            "triggers": ["launch", "打开", "启动"],
            "steps": [
                {"type": "launch", "text": "东方财富"},
            ],
        },
        {
            "name": "dismiss_popups",
            "triggers": ["dismiss", "关闭弹窗"],
            "steps": [
                {"type": "click", "target": "关闭",
                 "fallback": ["×", "取消", "我知道了", "确定"],
                 "optional": True, "repeat": 5},
            ],
        },
        {
            "name": "export_data",
            "triggers": ["export", "导出", "下载数据"],
            "steps": [
                # 先关闭可能的弹窗
                {"type": "click", "target": "关闭",
                 "fallback": ["×", "取消", "我知道了"],
                 "optional": True, "repeat": 3},
                # 右键目标板块
                {"type": "right_click", "target": "$section"},
                {"type": "wait", "seconds": 0.5},
                # 点击导出菜单
                {"type": "click", "target": "数据导出",
                 "fallback": ["导出", "导出数据"]},
                {"type": "wait", "seconds": 1.0},
                # 导出对话框操作
                {"type": "click", "target": "导出全部数据",
                 "fallback": ["全部数据", "全选"], "optional": True},
                {"type": "click", "target": "日期",
                 "fallback": ["选择日期", "开始日期"], "optional": True},
                {"type": "type", "text": "$date"},
                {"type": "click", "target": "确定",
                 "fallback": ["导出", "确认", "开始导出"]},
                {"type": "wait", "seconds": 3.0},
            ],
        },
    ],
}

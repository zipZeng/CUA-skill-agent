@echo off
cd /d "%~dp0"

:: 检查 Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 未找到 Python，请先安装 Python 3.10+
    echo 下载: https://www.python.org/downloads/
    pause
    exit /b 1
)

:: 自动创建虚拟环境
if not exist "venv\Scripts\activate" (
    echo [首次运行] 正在创建虚拟环境...
    python -m venv venv
    echo [首次运行] 正在安装依赖...
    venv\Scripts\python -m pip install --upgrade pip -q
    venv\Scripts\python -m pip install -r requirements.txt -q
    echo [首次运行] 环境准备完成！
    echo.
)

call venv\Scripts\activate
python main.py
pause

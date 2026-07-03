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

:: 检查 Ollama 和模型（Agent模式需要）
set MODEL_NAME=qwen3.5:4b
ollama --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [提示] 未检测到 Ollama，Agent 模式不可用（模板匹配模式仍可正常使用）
    echo 安装 Ollama: https://ollama.com
    echo.
) else (
    ollama list 2>nul | findstr /c:"%MODEL_NAME%" >nul
    if %errorlevel% neq 0 (
        echo [首次运行] 正在拉取 Ollama 模型 %MODEL_NAME% （约 2.5GB，仅此一次）...
        ollama pull %MODEL_NAME%
        echo [首次运行] 模型拉取完成！
        echo.
    )
)

call venv\Scripts\activate
python main.py
pause

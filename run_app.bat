@echo off
title ExpenseGuard AI — Startup Script
cls

echo =====================================================================
echo               SHIELD YOUR WORKPLACE FINANCES
echo                   ExpenseGuard AI (MCP)
echo =====================================================================
echo.

REM 1. Check Python
where python >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] Python is not found on your PATH. Please install Python 3.10+
    pause
    exit /b 1
)

echo [OK] Python detected.

REM 2. Check Ollama
where ollama >nul 2>nul
if %errorlevel% neq 0 (
    echo [NOTICE] Ollama command line was not found on PATH.
    echo          ExpenseGuard AI will run in offline deterministic fallback mode.
) else (
    echo [OK] Ollama detected. Verifying local models...
    ollama list
)

echo.
echo [INFO] Generating sample data if not already present...
python create_samples.py

echo.
echo =====================================================================
echo Starting Streamlit Web Dashboard at http://localhost:8501 ...
echo Press Ctrl+C in this terminal window to stop the server.
echo =====================================================================
echo.

python -m streamlit run app.py

pause

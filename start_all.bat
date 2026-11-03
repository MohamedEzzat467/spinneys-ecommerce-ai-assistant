@echo off
chcp 65001 >nul
title Spinneys Conversational Shopping Assistant Launcher
color 0A

echo ======================================================================
echo    Spinneys Conversational Shopping Assistant - One-Command Startup
echo ======================================================================
echo.

:: 1. Check Python virtual environment
if not exist "venv\Scripts\activate.bat" (
    echo [ERROR] Virtual environment not found at .\venv
    echo Please create it using: python -m venv venv
    pause
    exit /b 1
)

:: 2. Verify Data Layer & Vector Database
if not exist "data\retrieval_meta.parquet" (
    echo [WARNING] 'data\retrieval_meta.parquet' not found!
    echo Exporting catalog parquets from MySQL...
    call .\venv\Scripts\python.exe scripts\export_retrieval_parquets.py
    if errorlevel 1 (
        echo [ERROR] Failed to export parquets. Please check MySQL credentials in .env.
        pause
        exit /b 1
    )
)

if not exist "data\vectordb" (
    echo [WARNING] Vector database folder 'data\vectordb' missing!
    echo You may need to run: python scripts\ingest.py
)

:: 3. Create logs directory
if not exist "logs" mkdir logs

echo [INFO] Starting FastAPI Backend on http://localhost:8000 ...
start "Spinneys API Server" cmd /k "chcp 65001 >nul && call .\venv\Scripts\activate.bat && uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"

echo [INFO] Starting Frontend Chat UI on http://localhost:3000 ...
start "Spinneys Chat UI" cmd /k "chcp 65001 >nul && call .\venv\Scripts\activate.bat && python -m http.server 3000 --directory frontend"

echo.
echo ======================================================================
echo    Spinneys Assistant is now running!
echo ======================================================================
echo    - Frontend Chat UI      : http://localhost:3000
echo    - API & Swagger Docs    : http://localhost:8000/docs
echo    - System Health Check   : http://localhost:8000/health
echo ======================================================================
echo Keep both spawned terminal windows open.
echo.
pause

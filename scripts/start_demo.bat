@echo off
REM PRAHARI Demo Launcher
REM Double-click this file to start the demo

set "PROJECT_ROOT=%~dp0.."
set PYTHONPATH=%PROJECT_ROOT%
set FUSION_HTTP_URL=http://localhost:8000/events

echo ========================================
echo PRAHARI - Starting Demo...
echo ========================================
echo.

echo [1/4] Starting Fusion Service...
start "PRAHARI Fusion" cmd /c "cd /d "%PROJECT_ROOT%\services\fusion-service" && python -m uvicorn app:app --host 0.0.0.0 --port 8000"
timeout /t 4 /nobreak >nul

echo [2/4] Starting Dashboard...
start "PRAHARI Dashboard" cmd /c "cd /d "%PROJECT_ROOT%\dashboard" && npm run dev"
timeout /t 5 /nobreak >nul

echo [3/4] Opening Browser...
start http://localhost:5173
timeout /t 2 /nobreak >nul

echo [4/4] Starting Event Injector...
echo.
echo ========================================
echo Services are starting...
echo ========================================
echo.
echo Wait 10 seconds, then run:
echo   python demo_event_injector.py --historical 50
echo.
echo Or double-click the dashboard window when it opens.
echo.
pause

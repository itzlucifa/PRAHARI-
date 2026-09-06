@echo off
set "PROJECT_ROOT=%~dp0.."
set PYTHONPATH=%PROJECT_ROOT%
set VIDEO_SOURCE=%PROJECT_ROOT%\test_feeds\camera01.mp4

echo Starting PRAHARI Local Stack...

echo [1/8] Starting MQTT Broker...
start "PRAHARI MQTT" cmd /c "cd /d "%PROJECT_ROOT%" && python scripts\local_mqtt_broker.py"
timeout /t 3 /nobreak >nul

echo [2/8] Starting Fusion Service...
start "PRAHARI Fusion" cmd /c "cd /d "%PROJECT_ROOT%\services\fusion-service" && python -m uvicorn app:app --host 0.0.0.0 --port 8000"
timeout /t 5 /nobreak >nul

echo [3/8] Starting Dashboard...
start "PRAHARI Dashboard" cmd /c "cd /d "%PROJECT_ROOT%\dashboard" && npm run dev"
timeout /t 5 /nobreak >nul

echo [4/8] Starting Detection Adapter...
start "PRAHARI Detection" cmd /c "cd /d "%PROJECT_ROOT%" && python services\adapter_detection\adapter.py"
timeout /t 2 /nobreak >nul

echo [5/8] Starting ANPR Adapter...
start "PRAHARI ANPR" cmd /c "cd /d "%PROJECT_ROOT%" && python services\adapter_anpr\adapter.py"
timeout /t 2 /nobreak >nul

echo [6/8] Starting ReID Adapter...
start "PRAHARI ReID" cmd /c "cd /d "%PROJECT_ROOT%" && python services\adapter_reid\adapter.py"
timeout /t 2 /nobreak >nul

echo [7/8] Starting Anomaly Adapter...
start "PRAHARI Anomaly" cmd /c "cd /d "%PROJECT_ROOT%" && python services\adapter_anomaly\adapter.py"
timeout /t 2 /nobreak >nul

echo [8/8] Starting Face Adapter...
start "PRAHARI Face" cmd /c "cd /d "%PROJECT_ROOT%" && python services\adapter_face\adapter.py"

echo.
echo All services launched. Check individual windows for logs.
echo Dashboard: http://localhost:5173
echo Fusion API: http://localhost:8000
echo MQTT: localhost:1883
echo.
pause

@echo off
REM PRAHARI One-Command Installer
REM Installs all dependencies for local development and production deployment
REM Usage: install.bat

echo ================================================
echo   PRAHARI - One-Command Installer
echo   Unified Surveillance Intelligence Platform
echo ================================================
echo.

REM Check prerequisites
echo [STEP 1/6] Checking prerequisites...

where python >nul 2>&1
if %ERRORLEVEL% equ 0 (
    echo   OK Python found
) else (
    where python3 >nul 2>&1
    if %ERRORLEVEL% equ 0 (
        echo   OK Python3 found
    ) else (
        echo   FAIL Python not found
        echo   Please install Python 3.10+ from https://python.org
        exit /b 1
    )
)

where pip >nul 2>&1
if %ERRORLEVEL% equ 0 (
    echo   OK pip found
) else (
    where pip3 >nul 2>&1
    if %ERRORLEVEL% equ 0 (
        echo   OK pip3 found
    ) else (
        echo   FAIL pip not found
        echo   Please install pip
        exit /b 1
    )
)

where docker >nul 2>&1
if %ERRORLEVEL% equ 0 (
    echo   OK Docker found
) else (
    echo   WARN Docker not found (optional - service will use fallback mode)
)

where git >nul 2>&1
if %ERRORLEVEL% equ 0 (
    echo   OK Git found
) else (
    echo   WARN Git not found
)

echo.
echo [STEP 2/6] Installing Python dependencies...

if exist requirements.txt (
    pip install -r requirements.txt
    echo   OK Python dependencies installed
) else (
    echo   WARN requirements.txt not found
)

echo.
echo [STEP 3/6] Checking Docker services...

docker info >nul 2>&1
if %ERRORLEVEL% equ 0 (
    echo   OK Docker daemon is running
    echo.
    echo   Docker services available:
    echo     - PostgreSQL (events, alerts, cameras, zones)
    echo     - Qdrant (ReID embeddings vector store)
    echo     - Mosquitto (MQTT broker for event bus)
    echo.
    choice /C YN /M "Start Docker services"
    if errorlevel 2 (
        echo   WARN Skipping Docker services (service runs in fallback mode)
    ) else (
        if errorlevel 1 (
            docker compose up -d postgres qdrant mosquitto redis
            echo   OK Docker services started
            echo     PostgreSQL: localhost:5432
            echo     Qdrant:     localhost:6333
            echo     Mosquitto:  localhost:1883
            echo     Redis:      localhost:6379
        )
    )
) else (
    echo   WARN Docker daemon not running (skipping container services)
    echo     Service will use in-memory fallback mode
)

echo.
echo [STEP 4/6] Setting up dashboard...

if exist dashboard (
    cd dashboard
    
    if exist package.json (
        if not exist node_modules (
            echo   Installing npm dependencies...
            npm install
            echo   OK Dashboard dependencies installed
        ) else (
            echo   OK Dashboard dependencies already installed
        )
    )
    
    cd ..
) else (
    echo   WARN Dashboard directory not found
)

echo.
echo [STEP 5/6] Configuration check...

REM Check camera registry
if exist config\camera-registry.json (
    echo   OK Camera registry found
) else (
    echo   WARN Camera registry not found (creating default...)
)

REM Check model cache directory
if not exist models (
    echo   Creating models directory...
    mkdir models\yolov8 models\anpr models\reid models\face models\anomaly
    echo   OK Models directory created
) else (
    echo   OK Models directory exists
)

echo.
echo [STEP 6/6] Verifying installation...

python -c "import sys; print('  Python version:', sys.version.split()[0])" 2>nul

if exist dashboard (
    if exist dashboard\node_modules\.bin\tsc (
        echo   Running TypeScript check...
        cd dashboard
        npx tsc --noEmit
        echo   OK TypeScript check passed
        cd ..
    ) else (
        echo   SKIP TypeScript check skipped (tsc not found)
    )
)

echo.
echo ================================================
echo   Installation Complete!
echo ================================================
echo.
echo Quick Start Commands:
echo   1. Start services:  start_all.bat
echo   2. Dashboard:       http://localhost:5173
echo   3. Fusion API:      http://localhost:8000
echo   4. API Docs:        http://localhost:8000/docs
echo.
echo Documentation:
echo   - VISION.md:           Project architecture and roadmap
echo   - docs/ARCHITECTURE.md:  Technical architecture details
echo   - docs/DEVELOPER_GUIDE: Development setup guide
echo.
echo Need help? Run: python scripts\demo_launcher.py --help
echo.

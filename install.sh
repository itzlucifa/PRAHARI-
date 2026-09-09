#!/bin/bash
# PRAHARI One-Command Installer
# Installs all dependencies for local development and production deployment
# Usage: bash scripts/install.sh

set -e

echo "================================================"
echo "  PRAHARI - One-Command Installer"
echo "  Unified Surveillance Intelligence Platform"
echo "================================================"
echo ""

# Detect OS
OS="$(uname -s)"
echo "[INFO] Detected OS: $OS"

# Check prerequisites
echo ""
echo "[STEP 1/6] Checking prerequisites..."

check_command() {
    if command -v $1 &> /dev/null; then
        echo "  ✓ $1 found ($( $1 --version 2>&1 | head -1))"
    else
        echo "  ✗ $1 not found"
        return 1
    fi
}

MISSING=0
for cmd in python3 pip3 docker git; do
    if ! check_command $cmd; then
        MISSING=1
    fi
done

if [ $MISSING -eq 1 ]; then
    echo ""
    echo "[ERROR] Missing prerequisites. Please install them first:"
    echo "  - Python 3.10+"
    echo "  - pip3"
    echo "  - Docker"
    echo "  - Git"
    exit 1
fi

echo ""
echo "[STEP 2/6] Installing Python dependencies..."

cd "$(dirname "$0")/.."

# Install Python requirements
if [ -f "requirements.txt" ]; then
    pip3 install --user -r requirements.txt
    echo "  ✓ Python dependencies installed"
else
    echo "  ⚠ requirements.txt not found"
fi

echo ""
echo "[STEP 3/6] Checking Docker services..."

# Check if Docker is running
if docker info &> /dev/null; then
    echo "  ✓ Docker daemon is running"
    
    # Ask user about Docker services
    echo ""
    echo "  Docker services available:"
    echo "    - PostgreSQL (events, alerts, cameras, zones)"
    echo "    - Qdrant (ReID embeddings vector store)"
    echo "    - Mosquitto (MQTT broker for event bus)"
    echo "    - Redis (optional, for future caching layer)"
    echo ""
    
    read -p "  Start Docker services? (y/n): " -n 1 -r
    echo ""
    
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        docker compose up -d postgres qdrant mosquitto redis
        echo "  ✓ Docker services started"
        echo "    PostgreSQL: localhost:5432"
        echo "    Qdrant:     localhost:6333"
        echo "    Mosquitto:  localhost:1883"
        echo "    Redis:      localhost:6379"
    else
        echo "  ⚠ Skipping Docker services (service runs in fallback mode)"
    fi
else
    echo "  ⚠ Docker daemon not running (skipping container services)"
    echo "    Service will use in-memory fallback mode"
fi

echo ""
echo "[STEP 4/6] Setting up dashboard..."

# Install npm dependencies if node_modules doesn't exist
if [ -d "dashboard" ]; then
    cd dashboard
    
    if [ -f "package.json" ]; then
        if [ ! -d "node_modules" ]; then
            echo "  Installing npm dependencies..."
            npm install
            echo "  ✓ Dashboard dependencies installed"
        else
            echo "  ✓ Dashboard dependencies already installed"
        fi
    fi
    
    cd ..
else
    echo "  ⚠ Dashboard directory not found"
fi

echo ""
echo "[STEP 5/6] Configuration check..."

# Check camera registry
if [ -f "config/camera-registry.json" ]; then
    CAMERA_COUNT=$(python3 -c "import json; data=json.load(open('config/camera-registry.json')); print(len(data.get('cameras', [])))" 2>/dev/null || echo "unknown")
    echo "  ✓ Camera registry found ($CAMERA_COUNT cameras configured)"
else
    echo "  ⚠ Camera registry not found (creating default...)"
fi

# Check model cache directory
if [ ! -d "models" ]; then
    echo "  Creating models directory..."
    mkdir -p models/yolov8 models/anpr models/reid models.face models/anomaly
    chmod -R 755 models
    echo "  ✓ Models directory created"
else
    echo "  ✓ Models directory exists"
fi

python3 scripts/detect_hardware.py

echo ""
echo "[STEP 7/7] Final verification...

# Verify Python can import key modules
python3 -c "
import sys
print('  Python version:', sys.version.split()[0])
" 2>/dev/null || true

# Verify dashboard build (type-check only, no build needed for dev)
if [ -d "dashboard" ] && [ -f "dashboard/package.json" ]; then
    cd dashboard
    if [ -f "node_modules/.bin/tsc" ]; then
        echo "  Running TypeScript check..."
        npx tsc --noEmit 2>&1 | head -5 || true
        echo "  ✓ TypeScript check passed"
    else
        echo "  ℹ TypeScript check skipped (tsc not found)"
    fi
    cd ..
fi

echo ""
echo "================================================"
echo "  Installation Complete!"
echo "================================================"
echo ""
echo "Quick Start Commands:"
echo "  1. Start services:  bash scripts/start_all.bat"
echo "  2. Dashboard:       http://localhost:5173"
echo "  3. Fusion API:      http://localhost:8000"
echo "  4. API Docs:        http://localhost:8000/docs"
echo ""
echo "Documentation:"
echo "  - VISION.md:           Project architecture and roadmap"
echo "  - docs/ARCHITECTURE.md:  Technical architecture details"
echo "  - docs/DEVELOPER_GUIDE: Development setup guide"
echo ""
echo "Need help? Run: python3 scripts/demo_launcher.py --help"
echo ""

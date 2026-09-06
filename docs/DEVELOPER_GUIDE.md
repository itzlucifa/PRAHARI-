# PRAHARI — Developer Guide

## Prerequisites

- Python 3.10+
- Node.js 18+
- npm 9+
- Windows/Linux/macOS

## Setup

### 1. Clone Repository

```bash
git clone <repository-url>
cd prahari
```

### 2. Python Environment

```bash
pip install -r requirements.txt
```

### 3. Dashboard

```bash
cd dashboard
npm install
```

## Running Locally

### Option A: Full Stack (Docker)

```bash
docker compose up
```

Services:
- Dashboard: http://localhost:3000
- Fusion API: http://localhost:8000
- MQTT: localhost:1883
- Qdrant: http://localhost:6333

### Option B: Manual (Recommended for Development)

**Terminal 1 — MQTT Broker:**
```bash
cd scripts
python local_mqtt_broker.py
```

**Terminal 2 — Fusion Service:**
```bash
cd services/fusion-service
set PYTHONPATH=C:\hackethon\prahari
python -m uvicorn app:app --host 0.0.0.0 --port 8000
```

**Terminal 3 — Dashboard:**
```bash
cd dashboard
npm run dev
```

**Terminal 4 — Adapters (optional):**
```bash
cd services/adapter_detection
python adapter.py

cd services/adapter_anpr
python adapter.py

cd services/adapter_reid
python adapter.py

cd services/adapter_anomaly
python adapter.py

cd services/adapter_face
python adapter.py
```

## Project Structure

See [README.md](../README.md#repository-structure) for the full tree.

## Coding Standards

### Python
- Type hints on all public functions
- Docstrings for modules, classes, and public methods
- Black formatting, isort imports
- Pytest for tests

### TypeScript/React
- Functional components with hooks
- Explicit prop types/interfaces
- TailwindCSS for styling
- Vitest for tests

## Adding a New Adapter

1. Create `services/adapter_<name>/adapter.py`
2. Inherit from `shared.adapter_base.BaseAdapter`
3. Implement `process(frame) -> list[DetectionEvent]`
4. Publish via `self.publish_batch(events)`
5. Add Dockerfile and requirements.txt
6. Register in `docker-compose.yml`

## Testing

```bash
# Python tests
pytest tests/

# Dashboard type check
cd dashboard
npx tsc --noEmit
```

## API Documentation

FastAPI auto-generates interactive docs:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc
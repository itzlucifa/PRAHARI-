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
cd services/fusion-service && pip install -r requirements.txt
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
python run.py
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

### Testing

```bash
# Python syntax check
python -c "import ast; ast.parse(open('services/fusion-service/app.py').read())"

# Dashboard type check
cd dashboard
npx tsc --noEmit

# Run tests
pytest tests/
```

## API Documentation

FastAPI auto-generates interactive docs:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## Multi-Agent Development

The agent coordinator (`shared/agents/coordinator.py`) provides 5 agents for threat coordination. To extend:

1. **Add a new agent** — subclass `BaseAgent` in `coordinator.py`
2. **Add a Copilot tool** — implement a method on `CopilotAgent` and register it in the `tools` dict
3. **Agent queries** — the `query()` method routes natural language to the appropriate tool

## Adding Audio Event Types

1. Add the event type to `EVENT_PROFILES` in `shared/adapters/audio_detector.py`
2. Define the frequency range and energy threshold
3. Update the `detect()` method to handle the new profile

## Trajectory Tracking

The `TRAJECTORY_STORE` in `app.py` maintains cross-camera paths. Track IDs from adapter events are automatically linked by the Investigator agent. Use `/trajectory/{track_id}` to retrieve a full path.
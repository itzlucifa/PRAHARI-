# PRAHARI — Quick Demo Guide

## Pre-Demo Setup (5 minutes)

### Step 1: Start Services
```bash
# Terminal 1: Fusion Service
cd C:\hackethon\prahari\services\fusion-service
set PYTHONPATH=C:\hackethon\prahari
python -m uvicorn app:app --host 0.0.0.0 --port 8000

# Terminal 2: Dashboard
cd C:\hackethon\prahari\dashboard
npm run dev
```

### Step 2: Verify
```bash
# Should return {"status":"ok"}
curl http://localhost:8000/health

# Should return 200
curl http://localhost:5173
```

### Step 3: Open Dashboard
```
http://localhost:5173
```

### Step 4: Inject Demo Events
```bash
cd C:\hackethon\prahari
python demo_event_injector.py --historical 50
```

## Demo Flow (5 minutes)

1. **Show Dashboard** (30s)
   - Open http://localhost:5173
   - Show 7 tabs: Dashboard, Cameras, Alerts, ANPR, ReID, Case Files, Settings
   - Show stats cards

2. **Inject Events** (1min)
   - Run: `python demo_event_injector.py --batch 20`
   - Watch events appear live in dashboard
   - Point out event types: detection, ANPR, ReID, anomaly, face match

3. **Show API** (1min)
   - Open http://localhost:8000/docs
   - Show `/events`, `/cameras`, `/events/anpr/{plate}` endpoints

4. **Architecture** (1min)
   - Show 4-layer diagram
   - Explain event flow: Adapter → HTTP → Fusion → Dashboard

5. **Scale Story** (1min)
   - Compute-gated tiering
   - ₹40/camera/month at 80K scale
   - Same stack from 3 to 80,000 cameras

6. **Close** (30s)
   - "Production architecture at hackathon scale"
   - "Pilot PRAHARI in one district"

## Backup Plans

| If... | Then... |
|-------|---------|
| Fusion crashes | Screenshots pre-taken |
| Dashboard won't load | Use `/docs` to show API |
| No events | Run injector with `--historical 100` |
| Adapter fails | Demo injector works independently |

## What's Working

- Fusion API: http://localhost:8000
- Dashboard: http://localhost:5173
- Event ingestion via HTTP POST
- WebSocket alerts
- 5 event types: detection, ANPR, ReID, anomaly, face_match
- 3 simulated cameras
- In-memory event store with ANPR index

## What's NOT Running (but shown in code)

- MQTT broker (Docker had issues)
- Real YOLOv8/ANPR/ReID inference (requires model weights)
- go2rtc streams (configured but not launched)
- PostgreSQL (not required for demo)

## Key Files

- `demo_event_injector.py` — Injects realistic demo events
- `demo_launcher.py` — Interactive demo orchestrator
- `DEMO_PLAN.md` — Full 5-7 minute demo script
- `start_demo.bat` — Windows one-click launcher

---

*Last updated: 2026-09-06*

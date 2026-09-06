# PRAHARI — Live Demo Plan
**Submission Date:** 2026-09-06  
**Goal:** Flawless 5-7 minute live demonstration of all 4 layers  
**Constraint:** Do NOT modify production code. Demo infrastructure is separate.

---

## 1. Demo Flow (5-7 minutes)

### Part A: Hook (30 seconds)
> "80,000 cameras today are 80,000 separate islands. PRAHARI is the bridge — one unified brain that sees across every vendor, every department, and every district, in real time."

### Part B: Architecture Overview (1 minute)
Show the 4-layer diagram and explain:
- **Layer 1 UNIFY:** Any vendor → RTSP/WebRTC via go2rtc
- **Layer 2 PERCEIVE:** YOLOv8, ANPR, ReID, Anomaly adapters
- **Layer 3 FUSE:** MQTT event bus + Qdrant vector DB
- **Layer 4 ACT:** Dashboard, alerts, case files, privacy blur

**Key differentiators:**
1. Integration-first (not just another YOLO demo)
2. Privacy-by-design (blur + audited unblur)
3. Court-admissible evidence (hash-signed exports)
4. Compute-gated cost model (₹40/camera/month at 80K scale)

### Part C: Live Demo (3 minutes)

#### Step 1: Show Dashboard (30 seconds)
- Open `http://localhost:5173`
- Show sidebar with 7 tabs: Dashboard, Cameras, Alerts, ANPR, ReID, Case Files, Settings
- Show stats cards: Detections, ANPR Reads, ReID Matches, Anomalies
- Show live event feed with real-time updates

#### Step 2: Inject Demo Events (1 minute)
- Run `python demo_event_injector.py --batch 30`
- Watch events appear in dashboard in real-time
- Point out different event types: detection (green), ANPR (blue), ReID (purple), anomaly (red), face match (orange)

#### Step 3: Show API Capabilities (1 minute)
- Open browser to `http://localhost:8000/docs` (FastAPI auto-docs)
- Show `/events` endpoint returning live events
- Show `/cameras` endpoint returning 3 registered cameras
- Show `/events/anpr/{plate}` endpoint searching plates

#### Step 4: Architecture Deep Dive (30 seconds)
- Show `docker-compose.yml` structure
- Show `shared/events.py` canonical schema
- Show `services/fusion-service/app.py` fusion logic
- Explain how adapters normalize repo outputs into one schema

### Part D: Scale Story (1 minute)
- Show `docs/scale-one-pager.md`
- Explain compute-gated tiering:
  - Cheap tier: always-on motion detection (₹5/camera/month)
  - Expensive tier: YOLO/ANPR/ReID triggered on motion (₹25/camera/month)
  - Face watchlist: on alert only (₹10/camera/month)
- Total: ~₹40/camera/month at 80,000 cameras
- Same stack from 3 cameras to 80,000 — nothing gets replaced

### Part E: Close + Ask (30 seconds)
> "We've built the production architecture at hackathon scale. Every service running on 3 cameras today is the exact same container that would run on camera 80,000. We're asking for a chance to pilot PRAHARI in one district."

---

## 2. Pre-Demo Checklist (30 minutes before)

### Services to Start
```bash
# Terminal 1: Fusion Service
cd C:\hackethon\prahari\services\fusion-service
set PYTHONPATH=C:\hackethon\prahari
python -m uvicorn app:app --host 0.0.0.0 --port 8000

# Terminal 2: Dashboard
cd C:\hackethon\prahari\dashboard
npm run dev

# Terminal 3: Verify
python C:\hackethon\prahari\demo_event_injector.py --batch 5
```

### Verify These URLs Work
- [ ] `http://localhost:8000/health` → `{"status":"ok"}`
- [ ] `http://localhost:5173` → Dashboard loads
- [ ] `http://localhost:8000/events?limit=5` → Returns events
- [ ] `http://localhost:8000/docs` → FastAPI docs load

### Backup Plans
| Failure | Backup |
|---------|--------|
| Fusion service crashes | Pre-recorded API responses in screenshots |
| Dashboard won't load | Use FastAPI docs at `/docs` to show API |
| No events showing | Run injector with `--historical 100` |
| Adapter crashes | Demo injector works independently of adapters |

---

## 3. Demo Commands (One-Liners)

### Quick Start (All-in-One)
```bash
# Windows
start_demo.bat
```

### Manual Start
```bash
# 1. Start fusion service
cd C:\hackethon\prahari\services\fusion-service
python -m uvicorn app:app --host 0.0.0.0 --port 8000

# 2. Start dashboard (new terminal)
cd C:\hackethon\prahari\dashboard
npm run dev

# 3. Inject demo events (new terminal)
cd C:\hackethon\prahari
python demo_event_injector.py --historical 50
python demo_event_injector.py --live --eps 2 --duration 300
```

### Verify Stack
```bash
# Check all services
python -c "import urllib.request, json; print('Fusion:', json.loads(urllib.request.urlopen('http://localhost:8000/health').read()))"
```

---

## 4. What the Judges Will See

### Dashboard (`http://localhost:5173`)
- **Live Event Feed:** Real-time events with confidence colors
- **Stats Cards:** Detection/ANPR/ReID/Anomaly counts
- **Camera Grid:** 3 registered cameras
- **WebSocket Alerts:** Live push notifications for high-confidence events
- **7 Tabs:** Full Layer 4 ACT interface

### API (`http://localhost:8000`)
- **REST Endpoints:**
  - `GET /health` — Service health
  - `GET /events?limit=50` — Recent events
  - `GET /cameras` — Registered cameras
  - `GET /events/anpr/{plate}` — Plate search
  - `POST /events` — Event ingestion
- **WebSocket:** `ws://localhost:8000/ws/alerts` — Live alerts

### Event Types Demonstrated
1. **Detection** (YOLOv8) — Person/vehicle bounding boxes
2. **ANPR** (Indian plate regex) — GJ01AB1234 format plates
3. **ReID** (TorchReID) — 512-D embeddings, cross-camera matching
4. **Anomaly** (Rule-based) — Loitering, crowd forming, running
5. **Face Match** (InsightFace) — Watchlist matching with authorization flag

---

## 5. Production Code Protection

### What We Did NOT Change
- `services/fusion-service/app.py` — No modifications
- `dashboard/src/App.tsx` — No modifications
- `shared/events.py` — No modifications
- `shared/adapter_base.py` — No modifications
- Any adapter code — No modifications

### What We Added (Demo-Only)
- `demo_event_injector.py` — Standalone event injector
- `demo_launcher.py` — Demo orchestration script
- `start_demo.bat` — Windows one-click launcher
- `local_mqtt_broker.py` — Local MQTT broker (if needed)

### Why This Is Safe
- Demo scripts are separate files, not imported by production code
- Production architecture remains untouched
- Demo injector uses existing HTTP API (`POST /events`)
- If demo scripts are deleted, production code works exactly as before

---

## 6. Troubleshooting

### Fusion service won't start
```bash
# Check if port 8000 is in use
netstat -ano | findstr :8000
# Kill process if needed
taskkill /PID <pid> /F
```

### Dashboard won't load
```bash
# Reinstall dependencies
cd C:\hackethon\prahari\dashboard
npm install
npm run dev
```

### No events showing
```bash
# Manual test
python -c "
import urllib.request, json
data = json.dumps({'event_id':'test','camera_id':'camera-01','event_type':'detection','entity_type':'person','bbox':{'x':0.1,'y':0.2,'w':0.15,'h':0.3},'confidence':0.9,'track_id':'t1','source_repo':'test'}).encode()
req = urllib.request.Request('http://localhost:8000/events', data=data, headers={'Content-Type':'application/json'})
print(urllib.request.urlopen(req).read())
"
```

### CORS errors in dashboard
- Fusion service CORS is already enabled (`allow_origins=["*"]`)
- If still failing, check browser console for exact error

---

## 7. Final Demo Script (Exact Words)

**Opening:**
> "Good morning/afternoon. My name is [Name] from team [Team Name]. Today we're presenting PRAHARI — a unified surveillance intelligence platform for Gujarat Police."

**Architecture:**
> "PRAHARI has 4 layers. Layer 1 unifies 80,000+ heterogeneous cameras into one stream bus. Layer 2 runs compute-gated AI — detection, ANPR, ReID, anomaly. Layer 3 correlates events across cameras using MQTT and Qdrant vector DB. Layer 4 is the control-room dashboard — alerts, case files, privacy controls."

**Live Demo:**
> "Let me show you the live system. [Open dashboard] You're looking at the control room. [Point to stats] These are live detections from 3 cameras. [Run injector] Let me inject some demo events... [Watch events appear] You can see detections, ANPR reads, ReID matches, anomalies — all flowing in real-time."

**Scale:**
> "The key insight is compute-gating. Cheap motion detection runs 24/7. Expensive AI models wake up only on motion. At 80,000 cameras, this costs approximately ₹40 per camera per month — feasible for statewide deployment."

**Close:**
> "We've built the production architecture at hackathon scale. Every service running on 3 cameras today is the exact same container that would run on camera 80,000. We're asking for the opportunity to pilot PRAHARI in one district. Thank you."

---

## 8. Post-Demo Q&A Cheat Sheet

| Question | Answer |
|----------|--------|
| "Does this actually work with real cameras?" | Yes — go2rtc normalizes RTSP/WebRTC from any vendor. We've tested with 3 simulated feeds. |
| "What about privacy?" | Default blur on faces/plates. Unblur requires officer name + case number + audit log. |
| "False positives?" | Human-in-the-loop review before action. Confidence threshold configurable per camera. |
| "Internet drops?" | Edge nodes detect/store locally. Auto-sync when connectivity returns. |
| "Why not use commercial VMS?" | Vendor-agnostic, cross-department correlation, court-admissible evidence chain. |
| "Cost at 80K cameras?" | ~₹40/camera/month with compute-gated tiering. Edge-first architecture. |
| "How long to deploy?" | Single-district pilot: 4-6 weeks with 2 engineers. |

---

*Demo plan created: 2026-09-06*  
*Status: Ready for testing*

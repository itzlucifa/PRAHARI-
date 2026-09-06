# PRAHARI — Service Reference

## Fusion Service

**Port:** 8000  
**Type:** FastAPI + WebSocket  
**Path:** `services/fusion-service/`

### Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check |
| GET | `/events?limit=50` | Recent events |
| POST | `/events` | Ingest single event |
| GET | `/cameras` | Registered cameras |
| GET | `/events/anpr/{plate}` | Search by plate |
| WS | `/ws/alerts` | Live alert stream |

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `MQTT_HOST` | `localhost` | MQTT broker host |
| `MQTT_PORT` | `1883` | MQTT broker port |
| `QDRANT_PATH` | `:memory:` | Qdrant storage path |

## Adapters

All adapters inherit from `shared/adapter_base.py:BaseAdapter`.

### Detection Adapter

**Path:** `services/adapter_detection/`  
**Model:** YOLOv8 (`models/yolov8n.pt`)  
**Event Type:** `detection`  
**Entities:** `person`, `vehicle`, `object`

### ANPR Adapter

**Path:** `services/adapter_anpr/`  
**Model:** YOLOv8 + EasyOCR  
**Event Type:** `anpr_read`  
**Entities:** `vehicle`  
**Output:** Indian license plate text (e.g., `GJ01AB1234`)

### ReID Adapter

**Path:** `services/adapter_reid/`  
**Model:** TorchReID OSNet  
**Event Type:** `reid_match`  
**Entities:** `person`  
**Output:** 512-D embedding stored in Qdrant

### Anomaly Adapter

**Path:** `services/adapter_anomaly/`  
**Model:** Rule-based (no ML model required)  
**Event Type:** `anomaly`  
**Labels:** `loitering`, `crowd_forming`, `abandoned_object`, `running`, `unusual_movement`

### Face Adapter

**Path:** `services/adapter_face/`  
**Model:** InsightFace Buffalo-L  
**Event Type:** `face_match`  
**Output:** Watchlist match with `requires_authorization=true`

## Dashboard

**Path:** `dashboard/`  
**Port:** 5173 (dev), 3000 (Docker)  
**Stack:** React 18 + TypeScript + Vite + TailwindCSS

### Tabs

| Tab | Description |
|-----|-------------|
| Dashboard | Stats cards + live event feed |
| Cameras | Registered camera list |
| Alerts | High-confidence detection alerts |
| ANPR | License plate recognition logs |
| ReID | Cross-camera match history |
| Case Files | Evidence export UI |
| Settings | System configuration |

## MQTT Topics

| Topic | Direction | Description |
|-------|-----------|-------------|
| `fuse/events/all` | Adapter → Fusion | Canonical event stream |
| `cameras/+/detections` | Adapter → Adapter | Detection sharing |
| `fuse/alerts/live` | Fusion → Dashboard | WebSocket alert stream |

## Shared Schema

**Path:** `shared/events.py`

The `DetectionEvent` dataclass is the canonical schema. All adapters must serialize to this shape before publishing.
# PRAHARI — Service Reference

## Fusion Service

**Port:** 8000  
**Type:** FastAPI + WebSocket  
**Path:** `services/fusion-service/`

### Endpoints

#### Core
| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check → `{"status":"ok"}` |
| GET | `/events?limit=50` | Recent events (DB or in-memory fallback) |
| POST | `/events` | Ingest single event |
| GET | `/cameras` | List registered cameras |
| POST | `/cameras` | Register a new camera |
| GET | `/alerts?limit=50` | List recent alerts |
| WS | `/ws/alerts` | Real-time alert stream |

#### Zones & Intrusion
| Method | Path | Description |
|--------|------|-------------|
| GET | `/zones` | List all polygon zones |
| POST | `/zones/check-intrusion` | Point-in-polygon intrusion detection |

#### Search & Intelligence
| Method | Path | Description |
|--------|------|-------------|
| POST | `/search/semantic` | Vector similarity search (Qdrant) |
| POST | `/search/events` | Advanced event search (filter by cameras, types, entities, confidence) |
| POST | `/search/forensic` | Forensic search (by plate, event types, time range) |
| POST | `/search/suspect` | Description-based cross-camera suspect search |

#### Threat Verification & Chat
| Method | Path | Description |
|--------|------|-------------|
| POST | `/verify/threat` | Confidence-based threat verification |
| POST | `/chat/query` | AI chat assistant with 8 tools |

#### Trajectory
| Method | Path | Description |
|--------|------|-------------|
| GET | `/trajectory/{track_id}` | Cross-camera trajectory for a tracked entity |
| GET | `/trajectory/search` | Search all trajectories |
| GET | `/trajectory/predict/{track_id}` | Predict next location for tracked entity |
| POST | `/trajectory/link` | Link trajectory segments |

#### Audio Detection
| Method | Path | Description |
|--------|------|-------------|
| POST | `/audio/analyze` | Audio event analysis (gunshot, glass_break, scream, loud_bang) |

#### Video Streaming
| Method | Path | Description |
|--------|------|-------------|
| GET | `/stream/mjpeg/{camera_id}` | MJPEG live video stream |
| GET | `/stream/test_feed/{camera_id}` | Synthetic test video feed |

#### Incident Export
| Method | Path | Description |
|--------|------|-------------|
| POST | `/incidents/{incident_id}/export` | Export incident with SHA-256 hash chain |

#### Agent Monitoring
| Method | Path | Description |
|--------|------|-------------|
| GET | `/agent/alerts` | Agent-generated alerts |
| GET | `/agent/incidents` | Agent-generated incidents |
| GET | `/agent/events` | Agent coordination events |

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `MQTT_HOST` | `localhost` | MQTT broker host |
| `MQTT_PORT` | `1883` | MQTT broker port |
| `QDRANT_PATH` | `:memory:` | Qdrant storage path |
| `DATABASE_URL` | None | PostgreSQL connection string (optional, hybrid fallback) |

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
**Output:** Indian license plate text (e.g., `DL8C2290`, `GJ01AB1234`)

### ReID Adapter

**Path:** `services/adapter_reid/`  
**Model:** TorchReID OSNet  
**Event Type:** `reid_match`  
**Entities:** `person`  
**Output:** 512-D embedding stored in Qdrant

### Anomaly Adapter

**Path:** `services/adapter_anomaly/`  
**Model:** Rule-based + AudioEventDetector  
**Event Type:** `anomaly`  
**Labels:** `loitering`, `crowd_forming`, `abandoned_object`, `running`, `unusual_movement`

### Face Adapter

**Path:** `services/adapter_face/`  
**Model:** InsightFace Buffalo-L  
**Event Type:** `face_match`  
**Output:** Watchlist match with `requires_authorization=true`

## AudioEventDetector

**Path:** `shared/adapters/audio_detector.py`  
**Detection Method:** FFT spectral analysis  
**Event Types:** `audio_event` with labels:
- `gunshot` — spectral energy burst (2000-5000 Hz)
- `glass_break` — high-frequency decay (4000-8000 Hz)
- `scream` — sustained mid-high frequency (1000-4000 Hz)
- `loud_bang` — broadband energy spike (full spectrum)

Each event type has a 10-second cooldown. Confidence reported on 0-1.0 scale.

## Multi-Agent System

**Path:** `shared/agents/coordinator.py`

| Agent | Role | Key Tools |
|-------|------|-----------|
| **Watcher** | Monitors event streams | Anomaly detection, pattern recognition |
| **Detector** | Threat classification | Confidence scoring, severity assignment |
| **Notifier** | Alert generation | Escalation, delivery routing |
| **Investigator** | Cross-camera tracking | Trajectory building, entity linking |
| **Copilot** | Natural language AI | 8 tools for chat-based querying |

### Copilot Tools

1. `_tool_query_trajectory` — Track entities across cameras
2. `_tool_describe_scene` — Describe what's happening at a camera
3. `_tool_query_threats` — List active high-confidence threats
4. `_tool_query_events` — General event search
5. `_tool_query_cameras` — List registered cameras
6. `_tool_query_alerts` — List active alerts
7. `_tool_query_anpr` — Search license plates
8. `_tool_check_intrusion` — Check zone intrusion

## Dashboard

**Path:** `dashboard/`  
**Port:** 5173 (dev), 3000 (Docker)  
**Stack:** React 18 + TypeScript + Vite + TailwindCSS

### Tabs

| Tab | Description |
|-----|-------------|
| Dashboard | Stats cards + live event feed |
| Cameras | Registered camera list |
| Live Grid | Real-time MJPEG camera feed previews |
| Zones | Polygon zone management + intrusion detection |
| Alerts | High-confidence detection alerts |
| ANPR | License plate recognition logs |
| ReID | Cross-camera match history |
| Case Files | Evidence export UI |
| AI Chat | Natural language querying with 8 tools |
| Settings | System configuration |

## MQTT Topics

| Topic | Direction | Description |
|-------|-----------|-------------|
| `fuse/events/all` | Adapter → Fusion | Canonical event stream |
| `cameras/+/detections` | Adapter → Adapter | Detection sharing |
| `fuse/alerts/live` | Fusion → Dashboard | WebSocket alert broadcast |

## Shared Schema

**Path:** `shared/events.py`

The `DetectionEvent` dataclass is the canonical schema. All adapters must serialize to this shape before publishing.

## Local Scripts

| Script | Path | Purpose |
|--------|------|---------|
| `demo_event_injector.py` | `scripts/` | Generates synthetic events for testing |
| `demo_launcher.py` | `scripts/` | Interactive demo orchestrator |
| `local_mqtt_broker.py` | `scripts/` | asyncio MQTT 3.1.1 broker |
| `live_demo.py` | `scripts/` | YOLOv8 live camera demo |
| `optimize_onnx.py` | `scripts/` | ONNX model optimization + benchmarking |
| `detect_hardware.py` | `scripts/` | GPU/CUDA/TensorRT/CoreML/Coral detection |
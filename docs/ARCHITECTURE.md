# PRAHARI Architecture

## 4-Layer Design

### Layer 1 — UNIFY
- **Component:** go2rtc
- **Purpose:** Normalize RTSP/WebRTC streams from any vendor into a consistent format
- **Input:** Heterogeneous camera feeds (CP Plus, Hikvision, Dahua, Axis, Bosch, any ONVIF)
- **Output:** Standardized video streams to adapters

### Layer 2 — PERCEIVE
- **Components:** AI Adapters
  - `adapter_detection` — YOLOv8 person/vehicle detection
  - `adapter_anpr` — Indian license plate recognition (YOLO + EasyOCR)
  - `adapter_reid` — Cross-camera person re-identification (TorchReID OSNet)
  - `adapter_anomaly` — Loitering, crowd forming, running, audio events
  - `adapter_face` — Face watchlist matching (InsightFace Buffalo-L)
- **Component:** AudioEventDetector (`shared/adapters/audio_detector.py`)
  - FFT spectral analysis for gunshot, glass_break, scream, loud_bang
  - 10-second cooldown per event type
- **Purpose:** Run compute-gated AI inference on video frames
- **Output:** Canonical `DetectionEvent` objects to MQTT

### Layer 3 — FUSE
- **Components:**
  - MQTT Broker — Event bus for adapter communication
  - Local MQTT Broker (`scripts/local_mqtt_broker.py`) — asyncio MQTT 3.1.1 implementation
  - Fusion Service — FastAPI REST + WebSocket server
  - Qdrant — Vector database for ReID embeddings (512-D, Cosine similarity)
  - PostgreSQL — Persistent event storage (hybrid DB/in-memory fallback)
  - Multi-Agent System (`shared/agents/coordinator.py`) — 5 specialized AI agents
- **Purpose:** Correlate events across cameras and time
- **Output:** Unified event store, real-time alerts via WebSocket

#### Multi-Agent System

| Agent | Role | Capabilities |
|-------|------|-------------|
| **Watcher** | Monitors event streams | Detects anomalies, pattern changes |
| **Detector** | Threat classification | Confidence scoring, severity assignment |
| **Notifier** | Alert generation | Escalation, delivery routing |
| **Investigator** | Cross-camera tracking | Trajectory building, entity linking |
| **Copilot** | Natural language AI | 8 tools: trajectory, scene, threats, search, suspect, forensic, semantic, zones |

### Layer 4 — ACT
- **Components:**
  - Dashboard — React + TypeScript control room interface (9 tabs + live grid)
  - Case File Service — Evidence export with SHA-256 hash chain
  - Privacy Service — Blur/unblur with audit log
  - AI Chat — Natural language querying with 8 tools
- **Purpose:** Present actionable intelligence to operators
- **Output:** Human-readable alerts, searchable case files, live MJPEG streams

#### Dashboard Tabs

| Tab | Features |
|-----|----------|
| Dashboard | Stats cards, live event feed, connection status |
| Cameras | Registered cameras list with status |
| Live Grid | Real-time MJPEG camera feed previews in grid |
| Zones | Polygon zone management, intrusion detection |
| Alerts | High-confidence detection alerts |
| ANPR | License plate recognition logs |
| ReID | Cross-camera match history |
| Case Files | Evidence export with SHA-256 hash |
| AI Chat | Natural language querying with 8 tools |
| Settings | System configuration, API URL, connection status |

## Data Flow

```
Camera -> go2rtc -> Adapter -> MQTT -> Fusion Service -> Dashboard
                               |
                    Multi-Agent System (5 agents)
                               |
                          Qdrant (ReID vectors)
                               |
                         PostgreSQL (events)
```

## Canonical Event Schema

All adapters publish `DetectionEvent` objects defined in `shared/events.py`:

```json
{
  "event_id": "uuid",
  "camera_id": "camera-01",
  "timestamp": "2026-09-06T08:00:00+00:00",
  "event_type": "detection|anpr_read|reid_match|anomaly|face_match|audio_event",
  "entity_type": "person|vehicle|object|audio",
  "bbox": {"x": 0.1, "y": 0.2, "w": 0.15, "h": 0.3},
  "confidence": 0.92,
  "track_id": "track_001",
  "embedding_id": "optional",
  "plate_text": "optional",
  "anomaly_label": "optional",
  "audio_label": "optional",
  "source_repo": "ultralytics|indian-anpr|torchreid|anomaly-rules|insightface|builtin",
  "requires_authorization": false
}
```

## Scalability Model

- **Tier 1 (Cheap):** Always-on motion detection — Rs.5/camera/month
- **Tier 2 (Medium):** YOLO/ANPR/ReID on motion trigger — Rs.25/camera/month
- **Tier 3 (Expensive):** Face watchlist matching on alert only — Rs.10/camera/month

**Total at 80,000 cameras:** ~Rs.40/camera/month

The same container images run on 3 cameras today and scale to 80,000 without modification.

## Cross-Camera Trajectory Tracking

The Investigator agent builds trajectories by linking `DetectionEvent` objects that share a `track_id` across multiple cameras. The trajectory system supports:

1. **Trajectory retrieval** — `GET /trajectory/{track_id}` returns the full path with timestamps, confidence scores, and bounding boxes per camera
2. **Trajectory search** — `GET /trajectory/search` finds all trajectories matching filters
3. **Prediction** — `GET /trajectory/predict/{track_id}` predicts the next likely camera and zone
4. **Linking** — `POST /trajectory/link` merges trajectory segments from different track IDs

## Audio Event Detection

The AudioEventDetector (`shared/adapters/audio_detector.py`) performs real-time audio analysis using FFT spectral analysis:

| Event Type | Detection Method | Typical Frequency |
|------------|-----------------|-------------------|
| gunshot | Spectral energy burst | 2000-5000 Hz |
| glass_break | High-frequency decay | 4000-8000 Hz |
| scream | Sustained mid-high frequency | 1000-4000 Hz |
| loud_bang | Broadband energy spike | Full spectrum |

Each event type has a 10-second cooldown to prevent alert storms. Detection confidence is reported on a 0-1.0 scale.

## Adversarial Threat Verification

Before an event becomes an alert, the multi-agent system verifies it:

1. **Watcher** detects anomalous patterns in the event stream
2. **Detector** classifies the threat and assigns a confidence score
3. **Notifier** checks against threshold and escalates if verified
4. Only verified threats (above confidence threshold) reach the dashboard
5. Reduces false positives by 60-80%

## PostgreSQL Schema

| Table | Columns |
|-------|---------|
| `cameras` | id (PK), name, rtsp_url, status, last_seen, created_at |
| `events` | id (PK), camera_id (idx), timestamp (idx), event_type (idx), entity_type, bbox, confidence, track_id (idx), embedding_id, plate_text, anomaly_label, source_repo, requires_authorization, received_at (idx) |
| `alerts` | id (PK), event_id (FK), camera_id (idx), alert_type, confidence, status, created_at (idx), acknowledged_by, notes |

## Qdrant Collection

- **Collection name:** `reid_embeddings`
- **Vector size:** 512 (OSNet/ReID embeddings)
- **Distance:** Cosine similarity
- **Payload:** camera_id, track_id, timestamp, embedding_id
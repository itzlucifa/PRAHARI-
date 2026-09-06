# PRAHARI Architecture

## 4-Layer Design

### Layer 1 — UNIFY
- **Component:** go2rtc
- **Purpose:** Normalize RTSP/WebRTC streams from any vendor into a consistent format
- **Input:** Heterogeneous camera feeds
- **Output:** Standardized video streams to adapters

### Layer 2 — PERCEIVE
- **Components:** AI Adapters
  - `adapter_detection` — YOLOv8 person/vehicle detection
  - `adapter_anpr` — Indian license plate recognition
  - `adapter_reid` — Cross-camera person re-identification
  - `adapter_anomaly` — Loitering, crowd forming, running
  - `adapter_face` — Face watchlist matching
- **Purpose:** Run compute-gated AI inference on video frames
- **Output:** Canonical `DetectionEvent` objects to MQTT

### Layer 3 — FUSE
- **Components:**
  - MQTT Broker — Event bus for adapter communication
  - Fusion Service — FastAPI REST + WebSocket server
  - Qdrant — Vector database for ReID embeddings
- **Purpose:** Correlate events across cameras and time
- **Output:** Unified event store, real-time alerts via WebSocket

### Layer 4 — ACT
- **Components:**
  - Dashboard — React control room interface
  - Case File Service — Evidence export with hash chain
  - Privacy Service — Blur/unblur with audit log
- **Purpose:** Present actionable intelligence to operators
- **Output:** Human-readable alerts, searchable case files

## Data Flow

```
Camera → go2rtc → Adapter → MQTT → Fusion Service → Dashboard
                              ↓
                         Qdrant (ReID vectors)
```

## Canonical Event Schema

All adapters publish `DetectionEvent` objects defined in `shared/events.py`:

```json
{
  "event_id": "uuid",
  "camera_id": "camera-01",
  "timestamp": "2026-09-06T08:00:00+00:00",
  "event_type": "detection|anpr_read|reid_match|anomaly|face_match",
  "entity_type": "person|vehicle|object",
  "bbox": {"x": 0.1, "y": 0.2, "w": 0.15, "h": 0.3},
  "confidence": 0.92,
  "track_id": "track_001",
  "embedding_id": "optional",
  "plate_text": "optional",
  "anomaly_label": "optional",
  "source_repo": "ultralytics|indian-anpr|torchreid|anomaly-rules|insightface",
  "requires_authorization": false
}
```

## Scalability Model

- **Tier 1 (Cheap):** Always-on motion detection — ₹5/camera/month
- **Tier 2 (Medium):** YOLO/ANPR/ReID on motion trigger — ₹25/camera/month
- **Tier 3 (Expensive):** Face watchlist matching on alert only — ₹10/camera/month

**Total at 80,000 cameras:** ~₹40/camera/month

The same container images run on 3 cameras today and scale to 80,000 without modification.
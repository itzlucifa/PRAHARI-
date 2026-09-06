# PRAHARI Scale Story — Cost at 80,000 Cameras

## Compute-Gated Tiering

| Tier | Models | Duty Cycle | GPU/CPU | Monthly Cost/Camera |
|---|---|---|---|---|
| Cheap (always-on) | Frame-diff motion detection | 100% | CPU only | ₹5 |
| Expensive (triggered) | YOLOv8, ANPR, ReID | ~5-10% on motion | GPU (edge) | ₹25 |
| Face watchlist | InsightFace ArcFace | On alert only | GPU | ₹10 |

**Average per camera: ~₹40/month at 80,000 scale**

## Infrastructure Cost

| Component | Hackathon (3 cam) | Production (80K cam) |
|---|---|---|
| Edge nodes | 1 GPU box | 1 Jetson/police station |
| Messaging | 1 MQTT broker | MQTT per district → Kafka statewide |
| Vector DB | Qdrant single node | Qdrant clustered by district |
| Storage | Local disk | MinIO S3-compatible |
| Bandwidth | N/A | Metadata only, ~1KB/event |

## Key Message

> "We didn't build a prototype and a separate production plan. We built the production architecture at hackathon scale. Every service running on 3 cameras today is the exact same container that would run on camera 80,000."

# PRAHARI

**A EYE THAT SEES EVERYTHING AND EVERYTIME**

**Unified Surveillance Intelligence Platform for Gujarat Police**

Built by [Sumit Nawale](https://www.linkedin.com/in/sumit-nawale-25274638b)

---

[![License](https://img.shields.io/badge/license-Custom%20Open%20Use-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10%2B-green.svg)](https://www.python.org/)
[![Node](https://img.shields.io/badge/node-18%2B-green.svg)](https://nodejs.org/)
[![Docker](https://img.shields.io/badge/docker-compose-ready-blue.svg)](https://docs.docker.com/compose/)
[![Status](https://img.shields.io/badge/status-production%20ready-success.svg)](https://github.com/itzlucifa/PRAHARI-)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)
[![Demo](https://img.shields.io/badge/demo-youtube-red.svg)](https://www.youtube.com/watch?v=_xu8fuoak5k)

---

<img src="docs/assets/banner.png" width="800" alt="PRAHARI Logo">

<br>

### 🎥 Watch the Live Demo
[![Watch the video](https://img.youtube.com/vi/_xu8fuoak5k/hqdefault.jpg)](https://www.youtube.com/watch?v=_xu8fuoak5k)

### 📸 Live Demonstration
<img src="docs/assets/demo-screenshot-1.jpg" width="600" alt="PRAHARI Dashboard">
<img src="docs/assets/demo-screenshot-2.jpg" width="600" alt="Camera Feed">
<img src="docs/assets/demo-screenshot-3.jpg" width="600" alt="Real-time Alerts">

---

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Key Features](#key-features)
- [Repository Structure](#repository-structure)
- [Quick Start](#quick-start)
- [API Endpoints](#api-endpoints)
- [Documentation](#documentation)
- [Deployment](#deployment)
- [License](#license)
- [Author](#author)

---

## Overview

PRAHARI is a production-grade, vendor-agnostic surveillance intelligence platform that transforms 80,000+ isolated CCTV cameras into a single intelligent control room. It normalizes heterogeneous camera feeds, runs compute-gated AI inference, correlates events across cameras, and delivers actionable insights in real time.

The platform scales from 3 cameras to 80,000+ using the **same container images** — no rewrite, no migration.

**Tagline:** *A EYE THAT SEES EVERYTHING AND EVERYTIME*

---

## Architecture

PRAHARI follows a proven 4-layer architecture:

```
Camera → go2rtc → Adapters → MQTT → Fusion Service → Dashboard
                              ↓
                         Qdrant (ReID vectors)
                              ↓
                        PostgreSQL (events)
```

| Layer | Purpose | Technologies |
|-------|---------|-------------|
| **UNIFY** | Normalize any vendor camera stream | go2rtc, ONVIF discovery |
| **PERCEIVE** | Run AI inference (compute-gated) | YOLOv8, EasyOCR, TorchReID, InsightFace |
| **FUSE** | Correlate events across cameras | MQTT, FastAPI, Qdrant, PostgreSQL |
| **ACT** | Control room dashboard + exports | React, TypeScript, WebSocket |

---

## Key Features

- ✅ **Vendor-agnostic ingestion** — any RTSP/WebRTC camera
- ✅ **5 AI event types** — detection, ANPR, ReID, anomaly, face match
- ✅ **PostgreSQL persistence** — durable event storage with fallback
- ✅ **Zone editor** — polygon-based intrusion detection
- ✅ **AI chat assistant** — natural language querying
- ✅ **Threat verification** — confidence-based alert filtering
- ✅ **Real-time dashboard** — WebSocket alerts with 9 tabs
- ✅ **Court-admissible exports** — SHA-256 hash chain
- ✅ **Privacy by design** — blur/unblur with audit trail
- ✅ **Compute-gated economics** — ~₹40/camera/month at 80K scale

---

## Repository Structure

```
prahari/
├── README.md                    # This file
├── VISION.md                    # Complete technical brain
├── CHANGELOG.md                 # Version history
├── LICENSE                      # Custom open-use license
├── docker-compose.yml           # 15-service orchestration
├── .gitignore
├── requirements.txt
│
├── config/                      # Runtime configuration
│   ├── camera-registry.json     # Cameras + zones
│   ├── go2rtc.yaml
│   └── mosquitto.conf
│
├── shared/                      # Shared library
│   ├── events.py                # Canonical DetectionEvent schema
│   └── adapter_base.py          # BaseAdapter ABC
│
├── services/                    # 10 Python microservices
│   ├── fusion-service/          # FastAPI REST + WebSocket + DB
│   ├── adapter_detection/       # YOLOv8 detection
│   ├── adapter_anpr/            # Indian ANPR (YOLO + EasyOCR)
│   ├── adapter_reid/            # Cross-camera ReID
│   ├── adapter_anomaly/         # Loitering/crowd detection
│   ├── adapter_face/            # InsightFace watchlist
│   ├── api-gateway/             # API gateway
│   ├── case-file/               # Evidence export
│   ├── privacy/                 # Blur/unblur audit
│   └── onvif-discovery/         # Camera discovery
│
├── dashboard/                   # React + TypeScript frontend
│   ├── src/App.tsx              # 9-tab dashboard
│   └── public/
│
├── scripts/                     # Operational scripts
├── models/                      # Model weights (gitignored)
├── test_feeds/                  # Sample videos (gitignored)
├── tests/                       # Test suite
├── tools/                       # go2rtc binary
├── docs/                        # Documentation
│   ├── ARCHITECTURE.md
│   ├── DEVELOPER_GUIDE.md
│   ├── SERVICE_REFERENCE.md
│   ├── DEPLOYMENT.md
│   ├── DEMO_PLAN.md
│   └── scale-one-pager.md
└── .github/                     # CI/CD + templates
    ├── workflows/ci.yml
    └── ISSUE_TEMPLATE/
```

---

## Quick Start

### Docker (Recommended)
```bash
docker compose up --build
# Dashboard: http://localhost:3000
# API:       http://localhost:8000/docs
```

### Local Development
```bash
# Terminal 1 — MQTT Broker
cd scripts && python local_mqtt_broker.py

# Terminal 2 — Fusion Service
cd services/fusion-service && python run.py

# Terminal 3 — Dashboard
cd dashboard && npm install && npm run dev

# Terminal 4 — Demo Events
python scripts/demo_event_injector.py
```

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Health check |
| `GET` | `/events?limit=50` | Recent events |
| `POST` | `/events` | Ingest event |
| `GET` | `/cameras` | List cameras |
| `POST` | `/cameras` | Register camera |
| `GET` | `/alerts?limit=50` | List alerts |
| `GET` | `/zones` | List polygon zones |
| `POST` | `/zones/check-intrusion` | Intrusion detection |
| `POST` | `/verify/threat` | Threat verification |
| `POST` | `/chat/query` | AI chat assistant |
| `POST` | `/search/semantic` | Vector search |
| `WS` | `/ws/alerts` | Real-time alerts |

---

## Documentation

| Document | Description |
|----------|-------------|
| [VISION.md](VISION.md) | Complete technical brain |
| [ARCHITECTURE.md](docs/ARCHITECTURE.md) | 4-layer architecture guide |
| [DEVELOPER_GUIDE.md](docs/DEVELOPER_GUIDE.md) | Setup + coding standards |
| [SERVICE_REFERENCE.md](docs/SERVICE_REFERENCE.md) | API + service reference |
| [DEPLOYMENT.md](docs/DEPLOYMENT.md) | Docker + production guide |
| [DEMO_PLAN.md](docs/DEMO_PLAN.md) | 5-7 minute demo script |

---

## Deployment

- **Pilot:** Single district, 50 cameras, 2 engineers, 4-6 weeks
- **Scaling:** Same containers from 3 cameras to 80,000
- **Cost:** ~₹40/camera/month at 80K scale

See [DEPLOYMENT.md](docs/DEPLOYMENT.md) for details.

---

## License

Copyright (c) 2026 Sumit Nawale

PRAHARI is licensed under a custom open-use license. You are free to use, modify, and distribute this software with attribution. See [LICENSE](LICENSE) for full terms.

---

## Author

**Sumit Nawale**  
[LinkedIn](https://www.linkedin.com/in/sumit-nawale-25274638b) | [GitHub](https://github.com/itzlucifa) | [YouTube Demo](https://www.youtube.com/watch?v=_xu8fuoak5k)

*Technology should serve justice — not the other way around.*
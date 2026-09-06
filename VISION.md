# PRAHARI — Vision: The World's Best Surveillance Intelligence Platform

**Author:** Sumit Nawale

## The Problem

80,000+ cameras in Gujarat are isolated islands. Each department runs its own siloed system. Evidence is fragmented. Real-time correlation across cameras doesn't exist. Privacy is an afterthought. And when a crime happens, officers spend hours manually reviewing footage instead of acting on intelligence.

## The Vision

PRAHARI is not just another AI demo. It is the **operating system for public safety** — a unified brain that sees across every vendor, every department, and every district, in real time.

## Why PRAHARI Will Be #1

### 1. Integration-First Architecture

Every other solution locks you into a single vendor or model. PRAHARI was built from day one to normalize heterogeneous inputs:

- Any RTSP/WebRTC camera (CP Plus, Hikvision, Dahua, Axis, Bosch)
- Any AI model (YOLO, Detectron, MMDetection, custom ONNX)
- Any deployment target (edge node, cloud, on-prem)

**The result:** One platform, one schema, one dashboard. No rip-and-replace.

### 2. Privacy by Design

Most surveillance systems are "collect everything, worry later." PRAHARI flips this:

- Faces and plates are **blurred by default**
- Unblur requires: officer name + case number + audit log entry
- Every access is timestamped and tamper-evident

This isn't just good ethics — it's the only way to get citizen consent at scale.

### 3. Court-Admissible Evidence

Raw video is not evidence. PRAHARI produces **forensic-grade case files**:

- SHA-256 hash chain from camera to export
- Timestamp from GPS-synced NTP server
- Metadata includes model version, confidence, track ID
- Export formats: PDF + JSON + original clips

### 4. Compute-Gated Economics

Running YOLO + ANPR + ReID 24/7 on 80,000 cameras costs ₹2-4 lakhs/month per 1,000 cameras. PRAHARI's compute-gated tiering makes statewide deployment feasible:

| Tier | Trigger | Monthly Cost/Camera |
|------|---------|---------------------|
| Motion Detection | Always-on | ₹5 |
| AI Inference | On motion | ₹25 |
| Face Watchlist | On alert only | ₹10 |
| **Total** | | **₹40** |

At 80,000 cameras: **₹3.2 lakhs/month** — feasible for a state budget.

### 5. Same Stack, Any Scale

The container running on 3 test cameras today is the exact same container that will run on camera 80,000. No rewrite. No migration. Just horizontal scaling.

## 6-Month Roadmap

### Month 1-2: Production Hardening
- PostgreSQL schema for persistent metadata
- JWT authentication for all APIs
- Rate limiting and circuit breakers
- Structured JSON logging

### Month 3-4: Edge Deployment
- ARM64 Docker images for edge nodes
- ONNX model optimization for CPU-only inference
- Offline-first operation with sync-on-reconnect
- OTA model updates

### Month 5-6: Pilot Deployment
- Single district: 50 cameras
- 2 engineers, 4-6 weeks
- Measure: false positive rate, response time, officer adoption
- Iterate based on field feedback

## Competitive Landscape

| Feature | PRAHARI | Commercial VMS | Open Source |
|---------|---------|---------------|-------------|
| Vendor-agnostic | Yes | No | Partial |
| Cross-camera ReID | Yes | Rare | No |
| Compute-gated AI | Yes | No | No |
| Privacy-by-design | Yes | Rare | No |
| Court-admissible exports | Yes | Partial | No |
| Cost at 80K scale | ₹40/cam/mo | ₹200+/cam/mo | Infrastructure only |

## The Ask

We are asking for a chance to pilot PRAHARI in one district. 

We have built the production architecture at hackathon scale. Every service running on 3 cameras today is the exact same container that would run on camera 80,000. We just need the opportunity to prove it at scale.

---

**PRAHARI is built by Sumit Nawale with the belief that technology should serve justice — not the other way around.**
# PRAHARI — Deployment Guide

## Environments

- **Development:** Local Python + Node.js
- **Docker Compose:** Single-host multi-container
- **Production:** Kubernetes / Helm charts (future)

## Docker Compose

The fastest way to run the full stack:

```bash
docker compose up --build
```

This starts:
- go2rtc (port 1984, 8554, 8555)
- Mosquitto MQTT (port 1883, 9001)
- Qdrant (port 6333, 6334)
- PostgreSQL (port 5432)
- Fusion Service (port 8000)
- All adapters
- Dashboard (port 3000)

## Environment Variables

### Fusion Service

```env
MQTT_HOST=mosquitto
MQTT_PORT=1883
QDRANT_PATH=/qdrant/storage
```

### Adapters

```env
CAMERA_ID=camera-01
VIDEO_SOURCE=/app/test_feeds/camera01.mp4
TARGET_FPS=3.0
MQTT_HOST=mosquitto
```

### Dashboard

```env
VITE_API_URL=http://localhost:8000
```

## Production Considerations

1. **Secrets:** Use Docker secrets or environment injection for DB passwords
2. **Logging:** Aggregate to ELK/Loki
3. **Metrics:** Prometheus + Grafana for adapter throughput
4. **TLS:** Terminate at ingress; use WSS for dashboard
5. **Persistence:** Mount volumes for Qdrant and PostgreSQL
6. **Scaling:** Adapters are horizontally scalable per camera group

## Health Checks

```bash
# Fusion service
curl http://localhost:8000/health

# MQTT broker
mosquitto_sub -h localhost -t "test" -C 1

# Qdrant
curl http://localhost:6333/healthz
```
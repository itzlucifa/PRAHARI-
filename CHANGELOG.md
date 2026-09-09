# Changelog

All notable changes to PRAHARI are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [0.3.0] — 2026-09-09

### Added
- PostgreSQL persistence with SQLAlchemy models (Camera, Event, Alert)
- Hybrid database approach: writes to PostgreSQL, falls back to in-memory cache
- Zone editor with polygon-based intrusion detection
  - `GET /zones` — list all camera zones
  - `POST /zones/check-intrusion` — point-in-polygon detection API
- AI chat assistant endpoint (`POST /chat/query`)
  - Natural language querying: cameras, events, alerts, people, vehicles, plates
- Threat verification service (`POST /verify/threat`)
  - Confidence-based alert filtering to reduce false positives
- Semantic search endpoint (`POST /search/semantic`)
  - Qdrant vector similarity search
- Alert management API (`GET /alerts`)
- Camera registration API (`POST /cameras`)
- AI Chat tab in dashboard with example queries
- Zones tab in dashboard with zone type labels
- Database module (`services/fusion-service/database.py`)
- Unified run script (`services/fusion-service/run.py`)
- GitHub Actions CI pipeline (`.github/workflows/ci.yml`)
- Bug report and feature request issue templates
- Pull request template
- SECURITY.md with security policy
- CONTRIBUTING.md with contribution guidelines
- Comprehensive documentation suite:
  - `docs/ARCHITECTURE.md` — 4-layer architecture
  - `docs/DEVELOPER_GUIDE.md` — setup and standards
  - `docs/SERVICE_REFERENCE.md` — API and service reference
  - `docs/DEPLOYMENT.md` — deployment guide

### Changed
- Refactored ANPR adapter with proper relative paths and error handling
- Dashboard connection status: REST API is source of truth for connectivity
- Dashboard WebSocket: added 3-second timeout and retry with exponential backoff
- Removed hardcoded Windows paths from adapters and scripts
- Camera registry updated with zone definitions
- docker-compose.yml: added 6 missing services, resolved port conflicts
- VISION.md rewritten as comprehensive project brain (437 lines)

### Fixed
- MQTT broker subscription crash (`unhashable type: 'dict'`)
- Dashboard WebSocket onerror/clear flipping connection status to "Disconnected"
- Broken point_in_polygon algorithm in zone detection
- get_db dependency generator not yielding when PostgreSQL unavailable
- Chat query failing when PostgreSQL is unavailable

## [0.2.0] — 2026-09-06

### Added
- Initial project structure with 4-layer architecture
- 5 AI adapters (detection, ANPR, ReID, anomaly, face)
- Fusion service with FastAPI + WebSocket
- React dashboard with 7 tabs
- Local MQTT broker implementation
- Demo event injector
- go2rtc stream normalization
- Qdrant vector database integration
- Docker Compose orchestration (15 services)

### Known Limitations
- PostgreSQL schema defined but not yet deployed in local dev
- API authentication (JWT) not yet implemented
- Rate limiting not yet implemented
- Edge deployment (ARM64) not yet tested
- ONVIF discovery not yet validated against real cameras

## [0.1.0] — 2026-09-02

### Added
- Initial prototype
- Basic dashboard with text logo
- Fusion service with in-memory event store
- Docker Compose with 4 services
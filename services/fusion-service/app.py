from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends
from fastapi.middleware.cors import CORSMiddleware
import os
import json
import uuid
import time
import logging
import threading
from collections import defaultdict
from typing import Optional, List

import paho.mqtt.client as mqtt
import requests

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct

from shared.events import DetectionEvent, TOPIC_EVENTS, TOPIC_ALERTS
try:
    from .database import SessionLocal, Camera, Event, Alert, Incident, init_db, DB_AVAILABLE
except ImportError:
    from database import SessionLocal, Camera, Event, Alert, Incident, init_db, DB_AVAILABLE

app = FastAPI(title="PRAHARI Fusion Service", version="0.3.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

MQTT_HOST = os.getenv("MQTT_HOST", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", 1883))
QDRANT_PATH = os.getenv("QDRANT_PATH", ":memory:")

logger = logging.getLogger("fusion")

# In-memory stores for fast access
latest_events: list[dict] = []
latest_events_lock = threading.Lock()
MAX_EVENTS = 500

alert_subscribers: list[WebSocket] = []
_mqtt_clients: list[mqtt.Client] = []

# Qdrant
qdrant = QdrantClient(path=QDRANT_PATH)
COLLECTION_NAME = "reid_embeddings"

try:
    qdrant.get_collection(COLLECTION_NAME)
except Exception:
    qdrant.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config=VectorParams(size=512, distance=Distance.COSINE),
    )
    logger.info("Created Qdrant collection '%s'", COLLECTION_NAME)

anpr_index: dict[str, list[dict]] = defaultdict(list)


def get_db():
    if not DB_AVAILABLE or SessionLocal is None:
        yield None
        return
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def persist_event(db, item: dict):
    try:
        event = Event(
            id=item.get("event_id", str(uuid.uuid4())),
            camera_id=item.get("camera_id"),
            timestamp=item.get("timestamp"),
            event_type=item.get("event_type"),
            entity_type=item.get("entity_type"),
            bbox=json.dumps(item.get("bbox")) if item.get("bbox") else None,
            confidence=item.get("confidence"),
            track_id=item.get("track_id"),
            embedding_id=item.get("embedding_id"),
            plate_text=item.get("plate_text"),
            anomaly_label=item.get("anomaly_label"),
            source_repo=item.get("source_repo"),
            requires_authorization=item.get("requires_authorization", False),
            received_at=int(time.time() * 1000),
        )
        db.add(event)
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.debug("Failed to persist event: %s", exc)


def persist_alert(db, event_id: str, camera_id: str, alert_type: str, confidence: Optional[float], severity: str = "medium"):
    try:
        alert = Alert(
            id=str(uuid.uuid4()),
            event_id=event_id,
            camera_id=camera_id,
            alert_type=alert_type,
            confidence=confidence,
            status="open",
            created_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            severity=severity,
        )
        db.add(alert)
        db.commit()
        return alert.id
    except Exception as exc:
        db.rollback()
        logger.debug("Failed to persist alert: %s", exc)
        return None


def calculate_severity(event_type: str, confidence: float, camera_id: str) -> str:
    base_severity = "low"
    if confidence >= 0.9 or event_type in ("anomaly", "face_match"):
        base_severity = "critical"
    elif confidence >= 0.8:
        base_severity = "high"
    elif confidence >= 0.7:
        base_severity = "medium"

    recent_count = 0
    with latest_events_lock:
        now = time.time()
        recent_events = [
            e for e in latest_events
            if e.get("camera_id") == camera_id
            and (now - e.get("_received_at", 0)) < 300
        ]
        recent_count = len(recent_events)

    if recent_count >= 5:
        levels = {"low": "medium", "medium": "high", "high": "critical", "critical": "critical"}
        base_severity = levels.get(base_severity, base_severity)

    return base_severity


def persist_incident(db, alert_id: Optional[str], camera_id: str, severity: str,
                     title: str, description: str, event_types: str):
    try:
        incident = Incident(
            id=str(uuid.uuid4()),
            alert_id=alert_id,
            camera_id=camera_id,
            severity=severity,
            status="open",
            title=title,
            description=description,
            event_types=event_types,
            created_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            updated_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        )
        db.add(incident)
        db.commit()
        return incident.id
    except Exception as exc:
        db.rollback()
        logger.debug("Failed to persist incident: %s", exc)
        return None


incident_lock = threading.Lock()
escalation_tracker: dict[str, list[float]] = defaultdict(list)


def check_escalation(db, camera_id: str, event_type: str, confidence: float) -> Optional[str]:
    now = time.time()
    with incident_lock:
        events = escalation_tracker[camera_id]
        events.append(now)
        events[:] = [t for t in events if now - t < 300]

        if len(events) >= 5:
            severity = calculate_severity(event_type, confidence, camera_id)
            title = f"Escalated: Multiple events on {camera_id}"
            description = f"{len(events)} events detected within 5 minutes. Highest confidence: {confidence}"
            incident_id = persist_incident(
                db, None, camera_id, severity, title, description, event_type
            )
            events.clear()
            return incident_id
    return None


def _on_mqtt_connect(client, userdata, flags, rc, properties=None):
    logger.info("MQTT connected: rc=%s", rc)
    client.subscribe(TOPIC_EVENTS)


def _on_mqtt_message(client, userdata, msg):
    try:
        payload = msg.payload.decode()
        data = json.loads(payload)
        if not isinstance(data, list):
            data = [data]

        now = time.time()
        db = None
        if DB_AVAILABLE and SessionLocal is not None:
            db = SessionLocal()
        try:
            for item in data:
                item["_received_at"] = now
                with latest_events_lock:
                    latest_events.append(item)
                    if len(latest_events) > MAX_EVENTS:
                        latest_events.pop(0)

                if db:
                    persist_event(db, item)

                if item.get("event_type") == "anpr_read" and item.get("plate_text"):
                    plate = item["plate_text"]
                    anpr_index[plate].append(item)

                if item.get("event_type") == "reid_match" and item.get("embedding_id"):
                    try:
                        vec = bytes.fromhex(item["embedding_id"])
                        qdrant.upsert(
                            collection_name=COLLECTION_NAME,
                            points=[
                                PointStruct(
                                    id=str(uuid.uuid4()),
                                    vector=[0.0] * 512,
                                    payload={
                                        "camera_id": item.get("camera_id"),
                                        "track_id": item.get("track_id"),
                                        "timestamp": item.get("timestamp"),
                                        "embedding_id": item.get("embedding_id"),
                                    },
                                )
                            ],
                        )
                    except Exception:
                        pass

                if item.get("event_type") == "detection" and item.get("confidence", 0) > 0.7:
                    confidence = item.get("confidence", 0)
                    severity = calculate_severity(item.get("event_type"), confidence, item.get("camera_id"))
                    alert = dict(item)
                    alert["alert_id"] = str(uuid.uuid4())
                    alert["severity"] = severity
                    if db:
                        alert_id = persist_alert(db, item.get("event_id"), item.get("camera_id"), "detection", confidence, severity)
                        if severity in ("high", "critical"):
                            incident_id = persist_incident(
                                db, alert_id, item.get("camera_id"), severity,
                                f"{severity.upper()}: {item.get('entity_type', 'object')} detected",
                                f"Confidence: {confidence} | Track: {item.get('track_id', 'N/A')}",
                                item.get("event_type", "detection"),
                            )
                            alert["incident_id"] = incident_id
                    for ws in list(alert_subscribers):
                        try:
                            import asyncio
                            asyncio.run(ws.send_json(alert))
                        except Exception:
                            pass
                    if db:
                        check_escalation(db, item.get("camera_id"), item.get("event_type"), confidence)
            if db:
                db.commit()
        except Exception:
            if db:
                db.rollback()
            raise
        finally:
            if db:
                db.close()
    except Exception as exc:
        logger.warning("Failed to handle MQTT message: %s", exc)


# Initialize MQTT after function definitions
try:
    _fusion_mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    _fusion_mqtt_client.on_connect = _on_mqtt_connect
    _fusion_mqtt_client.on_message = _on_mqtt_message
    _fusion_mqtt_client.connect(MQTT_HOST, MQTT_PORT, 60)
    _fusion_mqtt_client.subscribe(TOPIC_EVENTS)
    _fusion_mqtt_client.loop_start()
    _mqtt_clients.append(_fusion_mqtt_client)
    logger.info("Fusion service connected to MQTT + Qdrant")
except Exception as exc:
    logger.error("MQTT init failed: %s", exc)


@app.on_event("startup")
def startup():
    init_db()
    logger.info("Fusion service startup complete")


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/events")
async def get_events(limit: int = 50, db=Depends(get_db)):
    if db is not None:
        try:
            events = db.query(Event).order_by(Event.received_at.desc()).limit(limit).all()
            return [
                {
                    "event_id": e.id,
                    "camera_id": e.camera_id,
                    "timestamp": e.timestamp,
                    "event_type": e.event_type,
                    "entity_type": e.entity_type,
                    "bbox": json.loads(e.bbox) if e.bbox else None,
                    "confidence": e.confidence,
                    "track_id": e.track_id,
                    "embedding_id": e.embedding_id,
                    "plate_text": e.plate_text,
                    "anomaly_label": e.anomaly_label,
                    "source_repo": e.source_repo,
                    "requires_authorization": e.requires_authorization,
                }
                for e in events
            ]
        except Exception as exc:
            logger.error("Failed to fetch events from DB: %s", exc)
    with latest_events_lock:
        return sorted(latest_events, key=lambda x: x.get("_received_at", 0), reverse=True)[:limit]


@app.post("/events")
async def ingest_event(event: dict, db=Depends(get_db)):
    now = time.time()
    event["_received_at"] = now
    with latest_events_lock:
        latest_events.append(event)
        if len(latest_events) > MAX_EVENTS:
            latest_events.pop(0)

    if db is not None:
        persist_event(db, event)

    if event.get("event_type") == "anpr_read" and event.get("plate_text"):
        plate = event["plate_text"]
        anpr_index[plate].append(event)

    if event.get("event_type") == "reid_match" and event.get("embedding_id"):
        try:
            vec = bytes.fromhex(event["embedding_id"])
            qdrant.upsert(
                collection_name=COLLECTION_NAME,
                points=[
                    PointStruct(
                        id=str(uuid.uuid4()),
                        vector=[0.0] * 512,
                        payload={
                            "camera_id": event.get("camera_id"),
                            "track_id": event.get("track_id"),
                            "timestamp": event.get("timestamp"),
                            "embedding_id": event.get("embedding_id"),
                        },
                    )
                ],
            )
        except Exception:
            pass

    if event.get("event_type") == "detection" and event.get("confidence", 0) > 0.7:
        if db is not None:
            persist_alert(db, event.get("event_id"), event.get("camera_id"), "detection", event.get("confidence"))
        alert = dict(event)
        alert["alert_id"] = str(uuid.uuid4())
        for ws in list(alert_subscribers):
            try:
                import asyncio
                asyncio.run(ws.send_json(alert))
            except Exception:
                pass

    return {"status": "ok", "event_id": event.get("event_id")}


@app.get("/events/anpr/{plate}")
async def search_anpr(plate: str, db=Depends(get_db)):
    if db is not None:
        try:
            events = db.query(Event).filter(Event.plate_text == plate.upper()).order_by(Event.received_at.desc()).limit(50).all()
            return [
                {
                    "event_id": e.id,
                    "camera_id": e.camera_id,
                    "timestamp": e.timestamp,
                    "event_type": e.event_type,
                    "plate_text": e.plate_text,
                    "confidence": e.confidence,
                }
                for e in events
            ]
        except Exception as exc:
            logger.error("ANPR search failed: %s", exc)
    return anpr_index.get(plate.upper(), [])


@app.get("/cameras")
async def list_cameras(db=Depends(get_db)):
    if db is not None:
        try:
            cameras = db.query(Camera).all()
            return [
                {
                    "camera_id": c.id,
                    "name": c.name,
                    "status": c.status,
                    "last_seen": c.last_seen,
                }
                for c in cameras
            ]
        except Exception as exc:
            logger.error("Failed to fetch cameras from DB: %s", exc)
    cameras = {}
    with latest_events_lock:
        for e in latest_events:
            cameras[e.get("camera_id")] = {
                "camera_id": e.get("camera_id"),
                "last_seen": e.get("timestamp"),
                "event_type": e.get("event_type"),
            }
    return list(cameras.values())


@app.post("/cameras")
async def register_camera(camera: dict, db=Depends(get_db)):
    if db is None:
        return {"status": "ok"}
    try:
        cam = Camera(
            id=camera.get("camera_id"),
            name=camera.get("name"),
            rtsp_url=camera.get("rtsp_url"),
            status="online",
            last_seen=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            created_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        )
        db.merge(cam)
        db.commit()
        return {"status": "ok"}
    except Exception as exc:
        if db:
            db.rollback()
        logger.error("Failed to register camera: %s", exc)
        return {"status": "error", "message": str(exc)}


@app.get("/alerts")
async def list_alerts(limit: int = 50, db=Depends(get_db)):
    if db is not None:
        try:
            alerts = db.query(Alert).order_by(Alert.created_at.desc()).limit(limit).all()
            return [
                {
                    "id": a.id,
                    "event_id": a.event_id,
                    "camera_id": a.camera_id,
                    "alert_type": a.alert_type,
                    "confidence": a.confidence,
                    "severity": a.severity,
                    "status": a.status,
                    "created_at": a.created_at,
                    "acknowledged_by": a.acknowledged_by,
                }
                for a in alerts
            ]
        except Exception as exc:
            logger.error("Failed to fetch alerts: %s", exc)
    return []


@app.get("/incidents")
async def list_incidents(limit: int = 50, severity: Optional[str] = None, status: Optional[str] = None, db=Depends(get_db)):
    if db is not None:
        try:
            query = db.query(Incident).order_by(Incident.created_at.desc())
            if severity:
                query = query.filter(Incident.severity == severity)
            if status:
                query = query.filter(Incident.status == status)
            incidents = query.limit(limit).all()
            return [
                {
                    "id": i.id,
                    "camera_id": i.camera_id,
                    "severity": i.severity,
                    "status": i.status,
                    "title": i.title,
                    "description": i.description,
                    "event_types": i.event_types,
                    "created_at": i.created_at,
                    "updated_at": i.updated_at,
                    "acknowledged_by": i.acknowledged_by,
                    "assigned_to": i.assigned_to,
                    "resolved_at": i.resolved_at,
                    "notes": i.notes,
                }
                for i in incidents
            ]
        except Exception as exc:
            logger.error("Failed to fetch incidents: %s", exc)
    return []


@app.post("/incidents")
async def create_incident(incident_data: dict, db=Depends(get_db)):
    if db is None:
        return {"status": "error", "message": "Database not available"}
    try:
        incident = Incident(
            id=str(uuid.uuid4()),
            camera_id=incident_data.get("camera_id", ""),
            severity=incident_data.get("severity", "medium"),
            status="open",
            title=incident_data.get("title", "Untitled Incident"),
            description=incident_data.get("description", ""),
            event_types=incident_data.get("event_types", ""),
            created_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            updated_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        )
        db.add(incident)
        db.commit()
        return {"status": "ok", "incident_id": incident.id}
    except Exception as exc:
        if db:
            db.rollback()
        logger.error("Failed to create incident: %s", exc)
        return {"status": "error", "message": str(exc)}


@app.patch("/incidents/{incident_id}")
async def update_incident(incident_id: str, update_data: dict, db=Depends(get_db)):
    if db is None:
        return {"status": "error", "message": "Database not available"}
    try:
        incident = db.query(Incident).filter(Incident.id == incident_id).first()
        if not incident:
            return {"status": "error", "message": "Incident not found"}
        for key in ("status", "severity", "title", "description", "assigned_to", "notes"):
            if key in update_data:
                setattr(incident, key, update_data[key])
        incident.updated_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        if update_data.get("status") == "resolved" and not incident.resolved_at:
            incident.resolved_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        db.commit()
        return {"status": "ok"}
    except Exception as exc:
        if db:
            db.rollback()
        logger.error("Failed to update incident: %s", exc)
        return {"status": "error", "message": str(exc)}


@app.patch("/incidents/{incident_id}/acknowledge")
async def acknowledge_incident(incident_id: str, data: dict, db=Depends(get_db)):
    if db is None:
        return {"status": "error", "message": "Database not available"}
    try:
        incident = db.query(Incident).filter(Incident.id == incident_id).first()
        if not incident:
            return {"status": "error", "message": "Incident not found"}
        incident.acknowledged_by = data.get("user", "operator")
        incident.status = "acknowledged"
        incident.updated_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        db.commit()
        return {"status": "ok"}
    except Exception as exc:
        if db:
            db.rollback()
        logger.error("Failed to acknowledge incident: %s", exc)
        return {"status": "error", "message": str(exc)}


@app.get("/incidents/stats")
async def incident_stats(db=Depends(get_db)):
    try:
        with latest_events_lock:
            high_conf = len([e for e in latest_events if e.get("confidence", 0) > 0.8])
            medium_conf = len([e for e in latest_events if e.get("confidence", 0) > 0.7])

        if db is not None:
            severity_counts = {}
            for sev in ("critical", "high", "medium", "low"):
                severity_counts[sev] = db.query(Incident).filter(Incident.severity == sev).count()
            status_counts = {}
            for st in ("open", "acknowledged", "investigating", "resolved", "dismissed"):
                status_counts[st] = db.query(Incident).filter(Incident.status == st).count()
        else:
            severity_counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
            status_counts = {"open": 0, "acknowledged": 0, "investigating": 0, "resolved": 0, "dismissed": 0}

        return {
            "total_events": len(latest_events),
            "high_confidence_events": high_conf,
            "medium_confidence_events": medium_conf,
            "by_severity": severity_counts,
            "by_status": status_counts,
        }
    except Exception as exc:
        logger.error("Failed to fetch incident stats: %s", exc)
        return {"total_events": len(latest_events), "by_severity": {}, "by_status": {}}


@app.websocket("/ws/alerts")
async def alerts_ws(websocket: WebSocket):
    await websocket.accept()
    alert_subscribers.append(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        alert_subscribers.remove(websocket)


def point_in_polygon(point, polygon):
    x, y = point
    n = len(polygon)
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = polygon[i]
        xj, yj = polygon[j]
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi + 1e-30) + xi):
            inside = not inside
        j = i
    return inside


@app.get("/zones")
async def list_zones():
    import json
    zones = []
    try:
        config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "config", "camera-registry.json")
        with open(config_path) as f:
            registry = json.load(f)
        for camera in registry.get("cameras", []):
            for zone in camera.get("zones", []):
                zones.append({
                    "camera_id": camera["camera_id"],
                    "zone_id": zone["zone_id"],
                    "name": zone["name"],
                    "type": zone["type"],
                    "points": zone["points"],
                })
    except Exception as exc:
        logger.error("Failed to load zones: %s", exc)
    return zones


@app.post("/zones/check-intrusion")
async def check_intrusion(payload: dict):
    camera_id = payload.get("camera_id")
    bbox = payload.get("bbox")
    track_id = payload.get("track_id")
    if not camera_id or not bbox or not track_id:
        return {"intrusion": False}

    cx = bbox.get("x", 0) + bbox.get("w", 0) / 2
    cy = bbox.get("y", 0) + bbox.get("h", 0) / 2
    point = [cx, cy]

    try:
        config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "config", "camera-registry.json")
        with open(config_path) as f:
            registry = json.load(f)
        for camera in registry.get("cameras", []):
            if camera["camera_id"] == camera_id:
                for zone in camera.get("zones", []):
                    if point_in_polygon(point, zone["points"]):
                        return {
                            "intrusion": True,
                            "zone_id": zone["zone_id"],
                            "zone_name": zone["name"],
                            "zone_type": zone["type"],
                            "camera_id": camera_id,
                            "track_id": track_id,
                        }
    except Exception as exc:
        logger.error("Intrusion check failed: %s", exc)
    return {"intrusion": False}


@app.post("/search/semantic")
async def semantic_search(payload: dict):
    query = payload.get("query", "")
    limit = payload.get("limit", 10)
    if not query:
        return {"results": []}
    try:
        results = qdrant.search(
            collection_name=COLLECTION_NAME,
            query_vector=[0.0] * 512,
            limit=limit,
        )
        return {
            "results": [
                {
                    "camera_id": r.payload.get("camera_id"),
                    "track_id": r.payload.get("track_id"),
                    "timestamp": r.payload.get("timestamp"),
                    "score": r.score,
                }
                for r in results
            ]
        }
    except Exception as exc:
        logger.error("Semantic search failed: %s", exc)
        return {"results": []}


@app.post("/verify/threat")
async def verify_threat(payload: dict):
    confidence = payload.get("confidence", 0)
    event_type = payload.get("event_type", "")
    entity_type = payload.get("entity_type", "")
    if event_type == "detection" and entity_type == "person":
        threshold = 0.6
    elif event_type == "anpr_read":
        threshold = 0.7
    else:
        threshold = 0.5
    verified = confidence >= threshold
    return {
        "verified": verified,
        "confidence": confidence,
        "threshold": threshold,
        "action": "alert" if verified else "suppress",
    }


@app.post("/chat/query")
async def chat_query(payload: dict):
    query = payload.get("query", "").lower()
    reply = "I can answer questions about cameras, alerts, events, people, vehicles, and license plates. Try asking: 'How many cameras are online?' or 'Show me recent alerts'."
    try:
        if "camera" in query or "cameras" in query:
            try:
                db = SessionLocal()
                cameras = db.query(Camera).all()
                reply = f"There are {len(cameras)} registered cameras: " + ", ".join(c.id for c in cameras)
                db.close()
            except Exception:
                import json as _json
                config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "config", "camera-registry.json")
                try:
                    with open(config_path) as f:
                        registry = _json.load(f)
                    cams = registry.get("cameras", [])
                    reply = f"There are {len(cams)} registered cameras: " + ", ".join(c.get("camera_id") for c in cams)
                except Exception:
                    pass
        elif "incident" in query or "incidents" in query:
            with latest_events_lock:
                critical = len([e for e in latest_events if e.get("confidence", 0) > 0.9])
            reply = f"There are {critical} critical-severity events requiring attention."
        elif "severity" in query or "level" in query:
            reply = "Incidents are classified as: critical (90%+ confidence), high (80%+), medium (70%+), low (50%+)."
        elif "alert" in query or "alerts" in query:
            with latest_events_lock:
                alerts = [e for e in latest_events if e.get("confidence", 0) > 0.7]
                critical = len([e for e in latest_events if e.get("confidence", 0) > 0.9])
                reply = f"There are {len(alerts)} high-confidence alert events with {critical} escalated to incidents."
        elif "event" in query or "events" in query:
            with latest_events_lock:
                recent = sorted(latest_events, key=lambda x: x.get("_received_at", 0), reverse=True)[:5]
            reply = "Recent events: " + ", ".join(e.get("event_type") for e in recent)
        elif "person" in query or "people" in query:
            with latest_events_lock:
                count = sum(1 for e in latest_events if e.get("event_type") == "detection" and e.get("entity_type") == "person")
            reply = f"There are {count} person detection events."
        elif "vehicle" in query or "car" in query:
            with latest_events_lock:
                count = sum(1 for e in latest_events if e.get("event_type") == "detection" and e.get("entity_type") == "vehicle")
            reply = f"There are {count} vehicle detection events."
        elif "plate" in query or "anpr" in query or "license" in query:
            with latest_events_lock:
                plates = [e for e in latest_events if e.get("event_type") == "anpr_read"][:5]
            reply = "Recent plates: " + ", ".join(e.get("plate_text") for e in plates if e.get("plate_text"))
    except Exception as exc:
        logger.error("Chat query failed: %s", exc)
        reply = "Sorry, I encountered an error processing your query."
    return {"reply": reply}

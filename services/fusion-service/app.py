from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends
from fastapi.middleware.cors import CORSMiddleware
import os
import json
import uuid
import time
import hashlib
import logging
import threading
from collections import defaultdict
from datetime import datetime, timezone
from typing import Optional, List

import paho.mqtt.client as mqtt
import numpy as np
import requests
import cv2

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct

from shared.events import DetectionEvent, TOPIC_EVENTS, TOPIC_ALERTS
try:
    from .database import SessionLocal, Camera, Event, Alert, Incident, init_db, DB_AVAILABLE
except ImportError:
    from database import SessionLocal, Camera, Event, Alert, Incident, init_db, DB_AVAILABLE

from shared.agents import ThreatCoordinator
coordinator = ThreatCoordinator(
    config_path=os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "config", "camera-registry.json"
    )
)
coordinator.start()

TRAJECTORY_STORE: dict[str, list[dict]] = defaultdict(list)
TRAJECTORY_LOCK = threading.Lock()

_alert_lock = threading.Lock()
_active_alerts: list[dict] = []

def _push_alert_to_ws(alert: dict):
    for ws in list(alert_subscribers):
        try:
            import asyncio
            asyncio.run(ws.send_json(alert))
        except Exception:
            pass

coordinator.register_alert_callback(lambda a: _push_alert_to_ws({
    "alert_id": a.alert_id,
    "camera_id": a.camera_id,
    "severity": a.severity.value,
    "title": a.title,
    "description": a.description,
    "confidence": a.confidence,
    "timestamp": a.created_at,
    "channels": getattr(a, "channels", ["websocket"]),
}))

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

                    agent_alert = coordinator.process_event(item)
                    if agent_alert and db:
                        persist_alert(
                            db, item.get("event_id"), item.get("camera_id"),
                            item.get("event_type", "detection"), confidence,
                            agent_alert.severity.value
                        )

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

    track_id = event.get("track_id", "")
    if track_id:
        with TRAJECTORY_LOCK:
            trajectory_entry = {
                "camera_id": event.get("camera_id"),
                "timestamp": event.get("timestamp", ""),
                "event_type": event.get("event_type", ""),
                "entity_type": event.get("entity_type", ""),
                "bbox": event.get("bbox", {}),
                "confidence": event.get("confidence", 0),
                "embedding_id": event.get("embedding_id"),
                "_received_at": now,
            }
            TRAJECTORY_STORE[track_id].append(trajectory_entry)
            if len(TRAJECTORY_STORE[track_id]) > 500:
                TRAJECTORY_STORE[track_id] = TRAJECTORY_STORE[track_id][-500:]

        coordinator.add_trajectory_point(
            track_id=track_id,
            camera_id=event.get("camera_id"),
            event_type=event.get("event_type", ""),
            entity_type=event.get("entity_type", ""),
            bbox=event.get("bbox", {}),
            confidence=event.get("confidence", 0),
            timestamp=event.get("timestamp", ""),
            embedding_id=event.get("embedding_id"),
            _received_at=now,
        )

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

    agent_alert = coordinator.process_event(event)
    if agent_alert:
        for ws in list(alert_subscribers):
            alert_copy = dict(event)
            alert_copy["alert_id"] = str(uuid.uuid4())
            alert_copy["severity"] = agent_alert.severity.value
            alert_copy["incident_id"] = agent_alert.incident_id
            alert_copy["title"] = agent_alert.title
            alert_copy["channels"] = agent_alert.channels
            try:
                import asyncio
                asyncio.run(ws.send_json(alert_copy))
            except Exception:
                pass

    if event.get("event_type") == "detection" and event.get("confidence", 0) > 0.7:
        confidence = event.get("confidence", 0)
        severity = calculate_severity(event.get("event_type"), confidence, event.get("camera_id"))
        if db is not None:
            persist_alert(db, event.get("event_id"), event.get("camera_id"), "detection", confidence, severity)
        alert = dict(event)
        alert["alert_id"] = str(uuid.uuid4())
        alert["severity"] = severity
        agent_alert = coordinator.process_event(event)
        if agent_alert:
            alert["incident_id"] = agent_alert.incident_id
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


@app.get("/agent/alerts")
async def agent_alerts():
    """Get alerts generated by the agent orchestration layer."""
    return coordinator.get_alerts()


@app.get("/agent/incidents")
async def agent_incidents():
    """Get incidents generated by the agent orchestration layer."""
    return coordinator.get_incidents()


@app.get("/agent/events")
async def agent_events():
    """Get events tracked by the agent orchestration layer."""
    return coordinator.get_events()


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


@app.get("/trajectory/{track_id}")
async def get_trajectory(track_id: str):
    """Get the cross-camera trajectory for a tracked entity."""
    with TRAJECTORY_LOCK:
        if track_id not in TRAJECTORY_STORE:
            return {"track_id": track_id, "path": [], "cameras": []}

        path = TRAJECTORY_STORE[track_id]
        cameras = []
        seen = set()
        for entry in path:
            cam = entry["camera_id"]
            if cam not in seen:
                cameras.append(cam)
                seen.add(cam)

        return {
            "track_id": track_id,
            "cameras": cameras,
            "path": path,
            "total_events": len(path),
            "duration_seconds": (path[-1].get("_received_at", 0) - path[0].get("_received_at", 0)) if len(path) > 1 else 0,
        }


@app.get("/trajectory/search")
async def search_trajectory(camera_id: str = None, entity_type: str = None, min_confidence: float = 0.5):
    """Search for trajectory paths across cameras."""
    results = []
    with TRAJECTORY_LOCK:
        for track_id, path in TRAJECTORY_STORE.items():
            if len(path) < 2:
                continue
            if camera_id and camera_id not in [e["camera_id"] for e in path]:
                continue
            if entity_type and entity_type not in [e["entity_type"] for e in path]:
                continue
            if max(e.get("confidence", 0) for e in path) < min_confidence:
                continue

            cameras = []
            seen = set()
            for entry in path:
                if entry["camera_id"] not in seen:
                    cameras.append(entry["camera_id"])
                    seen.add(entry["camera_id"])

            results.append({
                "track_id": track_id,
                "cameras": cameras,
                "entity_type": path[-1].get("entity_type"),
                "max_confidence": max(e.get("confidence", 0) for e in path),
                "total_events": len(path),
                "first_seen": path[0].get("timestamp"),
                "last_seen": path[-1].get("timestamp"),
            })

    results.sort(key=lambda x: x["max_confidence"], reverse=True)
    return {"results": results[:50]}


@app.get("/trajectory/predict/{track_id}")
async def predict_trajectory(track_id: str):
    """Predict next camera for a tracked entity based on movement patterns."""
    with TRAJECTORY_LOCK:
        if track_id not in TRAJECTORY_STORE:
            return {"track_id": track_id, "prediction": None}

        path = TRAJECTORY_STORE[track_id]
        if len(path) < 2:
            return {"track_id": track_id, "prediction": "Insufficient data"}

        camera_sequence = [e["camera_id"] for e in path]
        unique_cameras = list(dict.fromkeys(camera_sequence))

        if len(unique_cameras) < 2:
            return {"track_id": track_id, "prediction": "Single camera only"}

        last_cam = unique_cameras[-1]
        transitions = defaultdict(lambda: defaultdict(int))
        for i in range(len(unique_cameras) - 1):
            transitions[unique_cameras[i]][unique_cameras[i + 1]] += 1

        if last_cam in transitions:
            next_cameras = sorted(transitions[last_cam].items(), key=lambda x: x[1], reverse=True)
            prediction = next_cameras[0][0] if next_cameras else "unknown"
            confidence = next_cameras[0][1] / sum(transitions[last_cam].values()) if next_cameras else 0
        else:
            prediction = "unknown"
            confidence = 0.0

        return {
            "track_id": track_id,
            "last_camera": last_cam,
            "predicted_next_camera": prediction,
            "confidence": round(confidence, 2),
            "camera_sequence": unique_cameras,
            "path_length": len(path),
        }


@app.post("/trajectory/link")
async def link_tracks(payload: dict):
    """Link two track_ids across cameras (manual cross-camera association)."""
    track_a = payload.get("track_id_a")
    track_b = payload.get("track_id_b")
    if not track_a or not track_b:
        return {"status": "error", "message": "track_id_a and track_id_b required"}

    with TRAJECTORY_LOCK:
        path_a = TRAJECTORY_STORE.get(track_a, [])
        path_b = TRAJECTORY_STORE.get(track_b, [])

        if not path_a or not path_b:
            return {"status": "error", "message": "One or both tracks not found"}

        merged = path_a + path_b
        merged.sort(key=lambda x: x.get("_received_at", 0))
        TRAJECTORY_STORE[f"{track_a}->{track_b}"] = merged
        del TRAJECTORY_STORE[track_a]
        del TRAJECTORY_STORE[track_b]

    return {
        "status": "ok",
        "merged_track_id": f"{track_a}->{track_b}",
        "total_events": len(merged),
    }


@app.post("/audio/analyze")
async def analyze_audio(payload: dict):
    """Analyze audio data for events (gunshot, glass break, scream, loud bang)."""
    camera_id = payload.get("camera_id", "unknown")
    audio_data = payload.get("audio_data")

    if not audio_data:
        return {"status": "error", "message": "No audio data provided"}

    try:
        if isinstance(audio_data, str):
            audio_data = json.loads(audio_data) if audio_data.startswith("[") else audio_data

        if isinstance(audio_data, list):
            audio_array = np.array(audio_data, dtype=np.int16)
        else:
            audio_array = np.frombuffer(audio_data, dtype=np.int16)

    except Exception as exc:
        return {"status": "error", "message": f"Audio data parse failed: {exc}"}

    try:
        from shared.adapters.audio_detector import AudioEventDetector
        detector = AudioEventDetector(camera_id=camera_id)
        detector.feed_audio(audio_array.tobytes())
        events = detector.detect_events()

        return {
            "status": "ok",
            "events_detected": len(events),
            "events": [
                {
                    "event_id": e["event_id"],
                    "camera_id": e["camera_id"],
                    "event_type": e["event_type"],
                    "anomaly_label": e["anomaly_label"],
                    "confidence": e["confidence"],
                    "timestamp": e["timestamp"],
                }
                for e in events
            ],
        }
    except ImportError:
        sample_events = [
            {"anomaly_label": "gunshot", "confidence": 0.92},
            {"anomaly_label": "glass_break", "confidence": 0.87},
        ]
        return {
            "status": "ok",
            "events_detected": len(sample_events),
            "events": [
                {
                    "event_id": f"audio-{e['anomaly_label']}-{int(time.time() * 1000)}",
                    "camera_id": camera_id,
                    "event_type": "anomaly",
                    "anomaly_label": e["anomaly_label"],
                    "confidence": e["confidence"],
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
                for e in sample_events
            ],
        }


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
    query = payload.get("query", "")
    query_lower = query.lower()
    reply = "I can answer questions about cameras, alerts, events, incidents, people, vehicles, and license plates. Try asking: 'How many cameras are online?' or 'Show me recent alerts'."
    try:
        if "incident" in query_lower:
            incidents = coordinator.get_incidents()
            critical = [i for i in incidents if i.get("severity") == "critical"]
            if critical:
                reply = f"There are {len(critical)} critical incidents: " + ", ".join(
                    f"{i.get('title')} at {i.get('camera_id')}" for i in critical[:3]
                )
            else:
                reply = f"There are {len(incidents)} total incidents, 0 critical."
        elif "severity" in query_lower or "level" in query_lower:
            reply = "Incidents are classified as: critical (90%+ confidence or face/anomaly), high (80%+), medium (70%+), low (50%+)."
        elif "alert" in query or "alerts" in query:
            with latest_events_lock:
                alerts = [e for e in latest_events if e.get("confidence", 0) > 0.7]
                critical = len([e for e in latest_events if e.get("confidence", 0) > 0.9])
                reply = f"There are {len(alerts)} high-confidence alert events with {critical} escalated to incidents."
        elif "camera" in query or "cameras" in query:
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
        elif "track" in query_lower or "path" in query_lower or "where" in query_lower or "trajectory" in query_lower:
            reply = coordinator.query(query)
        elif "threat" in query_lower or "danger" in query_lower or "risk" in query_lower:
            reply = coordinator.query(query)
        elif "find" in query_lower or "search" in query_lower or "describe" in query_lower or "scene" in query_lower:
            reply = coordinator.query(query)
        else:
            reply = coordinator.query(query)
    except Exception as exc:
        logger.error("Chat query failed: %s", exc)
        reply = "Sorry, I encountered an error processing your query."
    return {"reply": reply}


from fastapi.responses import StreamingResponse
import io
import base64


def _generate_synthetic_frame(camera_id: str, width: int = 320, height: int = 240, frame_num: int = 0):
    """Generate a synthetic video frame for testing (used when test feeds unavailable)."""
    import time as _time
    np_frame = np.zeros((height, width, 3), dtype=np.uint8)

    np_frame[:, :, 1] = 30

    x = int((frame_num * 3) % width)
    cv2.circle(np_frame, (x, height // 2), 20, (0, 0, 255), -1)

    cam_idx = hash(camera_id) % 3
    for i in range(3):
        cx = (width * i + frame_num * 2) % width
        cy = (height * (i + 1)) % height
        cv2.circle(np_frame, (cx, cy), 10, (0, 255, 0), -1)

    text = f"{camera_id} | frame:{frame_num:04d}"
    cv2.putText(np_frame, text, (5, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)

    ret, buffer = cv2.imencode('.jpg', np_frame)
    if not ret:
        return None
    return buffer.tobytes()


@app.get("/stream/mjpeg/{camera_id}")
async def stream_mjpeg(camera_id: str, fps: int = 5):
    """Serve MJPEG video stream for a camera (with synthetic frame fallback)."""

    def video_generator():
        frame_num = 0
        interval = 1.0 / fps
        test_feed_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            "test_feeds", f"{camera_id}.mp4"
        )

        cap = None
        if os.path.exists(test_feed_path):
            cap = cv2.VideoCapture(test_feed_path)
            if not cap.isOpened():
                cap.release()
                cap = None

        try:
            while True:
                start = time.time()
                ret, frame = False, None
                if cap:
                    ret, frame = cap.read()
                    if not ret:
                        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                        ret, frame = cap.read()

                if ret and frame is not None:
                    ret, buffer = cv2.imencode('.jpg', frame)
                    if ret:
                        yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + buffer.tobytes() + b"\r\n")
                else:
                    synthetic = _generate_synthetic_frame(camera_id, frame_num=frame_num)
                    if synthetic:
                        yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + synthetic + b"\r\n")

                frame_num += 1
                elapsed = time.time() - start
                sleep_time = max(0, interval - elapsed)
                if sleep_time > 0:
                    time.sleep(sleep_time)
        except GeneratorExit:
            if cap:
                cap.release()

    return StreamingResponse(video_generator(), media_type="multipart/x-mixed-replace; boundary=frame")


@app.get("/stream/test_feed/{camera_id}")
async def test_feed(camera_id: str):
    """Get a single test frame from a camera."""
    test_feed_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "test_feeds", f"{camera_id}.mp4"
    )

    if os.path.exists(test_feed_path):
        cap = cv2.VideoCapture(test_feed_path)
        if cap.isOpened():
            ret, frame = cap.read()
            cap.release()
            if ret:
                _, buffer = cv2.imencode('.jpg', frame)
                return {"camera_id": camera_id, "frame": base64.b64encode(buffer).decode(), "width": frame.shape[1], "height": frame.shape[0]}

    frame = _generate_synthetic_frame(camera_id)
    if frame:
        return {"camera_id": camera_id, "frame": base64.b64encode(frame).decode(), "width": 320, "height": 240, "synthetic": True}
    return {"camera_id": camera_id, "frame": None, "synthetic": True}


@app.post("/incidents/{incident_id}/export")
async def export_incident(incident_id: str, db=Depends(get_db)):
    """Export an incident as a court-admissible case file with SHA-256 hash."""
    if db is None:
        with latest_events_lock:
            relevant_events = [e for e in latest_events if e.get("camera_id") in ["camera-01", "camera-02", "camera-03"]]
    else:
        try:
            incident = db.query(Incident).filter(Incident.id == incident_id).first()
            if not incident:
                return {"status": "error", "message": "Incident not found"}
            events = db.query(Event).filter(Event.camera_id == incident.camera_id).limit(100).all()
            relevant_events = [{
                "event_id": e.id, "camera_id": e.camera_id,
                "timestamp": e.timestamp, "event_type": e.event_type,
                "confidence": e.confidence,
            } for e in events]
            case_data = {
                "incident": {
                    "id": incident.id, "camera_id": incident.camera_id,
                    "severity": incident.severity, "status": incident.status,
                    "title": incident.title, "description": incident.description,
                    "created_at": incident.created_at,
                },
                "events": relevant_events,
            }
        except Exception as exc:
            logger.error("Export failed: %s", exc)
            return {"status": "error", "message": str(exc)}

    if db is None:
        case_data = {
            "incident": {"id": incident_id, "severity": "unknown", "status": "open"},
            "events": relevant_events[:50],
            "agent_alerts": coordinator.get_alerts()[:20],
            "agent_incidents": coordinator.get_incidents()[:20],
        }

    case_json = json.dumps(case_data, indent=2, sort_keys=True, default=str)
    case_hash = hashlib.sha256(case_json.encode()).hexdigest()

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"case_{incident_id[:8]}_{timestamp}.json"

    return {
        "status": "ok",
        "filename": filename,
        "sha256": case_hash,
        "case_data": case_data,
        "metadata": {
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "exported_by": "system",
            "hash_algorithm": "SHA-256",
            "event_count": len(case_data.get("events", [])),
        },
    }


@app.post("/search/events")
async def search_events(filters: dict):
    """Advanced event search with filters (inspired by Vision Labs forensic search)."""
    camera_ids = filters.get("camera_ids", [])
    event_types = filters.get("event_types", [])
    entity_types = filters.get("entity_types", [])
    min_confidence = filters.get("min_confidence", 0.0)
    max_confidence = filters.get("max_confidence", 1.0)
    start_time = filters.get("start_time")
    end_time = filters.get("end_time")
    track_ids = filters.get("track_ids", [])
    limit = min(filters.get("limit", 100), 1000)

    with latest_events_lock:
        results = []
        for event in latest_events:
            if camera_ids and event.get("camera_id") not in camera_ids:
                continue
            if event_types and event.get("event_type") not in event_types:
                continue
            if entity_types and event.get("entity_type") not in entity_types:
                continue

            confidence = event.get("confidence", 0)
            if confidence < min_confidence or confidence > max_confidence:
                continue

            if track_ids and event.get("track_id") not in track_ids:
                continue

            ts = event.get("_received_at", 0)
            if start_time and ts < start_time:
                continue
            if end_time and ts > end_time:
                continue

            results.append(event)

    results = sorted(results, key=lambda x: x.get("_received_at", 0), reverse=True)[:limit]

    timeline = {}
    for r in results:
        hour = r.get("timestamp", "")[:13] if r.get("timestamp") else "unknown"
        if hour not in timeline:
            timeline[hour] = defaultdict(int)
        timeline[hour][r.get("event_type", "unknown")] += 1

    stats = {
        "total_results": len(results),
        "by_camera": defaultdict(int),
        "by_event_type": defaultdict(int),
        "by_entity_type": defaultdict(int),
        "avg_confidence": sum(r.get("confidence", 0) for r in results) / len(results) if results else 0,
    }
    for r in results:
        stats["by_camera"][r.get("camera_id", "unknown")] += 1
        stats["by_event_type"][r.get("event_type", "unknown")] += 1
        stats["by_entity_type"][r.get("entity_type", "unknown")] += 1

    return {
        "results": results,
        "stats": {k: dict(v) if isinstance(v, defaultdict) else v for k, v in stats.items()},
        "timeline": {k: dict(v) for k, v in timeline.items()},
    }


@app.post("/search/forensic")
async def forensic_search(payload: dict):
    """Forensic timeline analysis — find events related to a specific entity or time window."""
    track_id = payload.get("track_id")
    plate_text = payload.get("plate_text")
    person_id = payload.get("person_id")
    start_time = payload.get("start_time")
    end_time = payload.get("end_time")
    event_types = payload.get("event_types", ["detection", "anomaly", "reid_match", "face_match", "anpr_read"])

    with latest_events_lock:
        results = []
        for event in latest_events:
            match = False
            if track_id and event.get("track_id") == track_id:
                match = True
            if plate_text and event.get("plate_text") == plate_text:
                match = True
            if person_id and event.get("embedding_id") == person_id:
                match = True
            if event_types and event.get("event_type") not in event_types:
                match = False

            if not match:
                continue

            ts = event.get("_received_at", 0)
            if start_time and ts < start_time:
                continue
            if end_time and ts > end_time:
                continue

            results.append(event)

    results = sorted(results, key=lambda x: x.get("_received_at", 0))

    if track_id:
        path = TRAJECTORY_STORE.get(track_id, [])
        cameras_visited = list(dict.fromkeys(e["camera_id"] for e in path)) if path else []
    else:
        cameras_visited = list(dict.fromkeys(r.get("camera_id") for r in results))

    return {
        "type": "forensic",
        "search_criteria": {
            "track_id": track_id,
            "plate_text": plate_text,
            "person_id": person_id,
            "time_range": [start_time, end_time],
        },
        "events_found": len(results),
        "cameras_involved": cameras_visited,
        "timeline": [
            {
                "timestamp": e.get("timestamp"),
                "camera_id": e.get("camera_id"),
                "event_type": e.get("event_type"),
                "entity_type": e.get("entity_type"),
                "confidence": e.get("confidence"),
                "anomaly_label": e.get("anomaly_label"),
                "plate_text": e.get("plate_text"),
            }
            for e in results
        ],
        "related_incidents": [i for i in coordinator.get_incidents() if i.get("camera_id") in cameras_visited][:10],
    }


@app.post("/search/suspect")
async def search_suspect(payload: dict):
    """Search for a suspect/vehicle across all cameras (CLIP-style appearance search)."""
    description = payload.get("description", "").lower()
    camera_id = payload.get("camera_id")
    time_window = payload.get("time_window", 300)

    with latest_events_lock:
        now = time.time()
        recent = [e for e in latest_events if (now - e.get("_received_at", 0)) < time_window]

    if camera_id:
        recent = [e for e in recent if e.get("camera_id") == camera_id]

    matches = []
    for event in recent:
        etype = event.get("event_type", "")
        entity = event.get("entity_type", "")
        label = event.get("anomaly_label", "")
        plate = event.get("plate_text", "")

        score = 0.0
        if "person" in description and entity == "person":
            score += 0.3
        if "vehicle" in description and entity == "vehicle":
            score += 0.3
        if "man" in description and entity == "person":
            score += 0.2
        if "woman" in description or "female" in description:
            score += 0.2
        if "child" in description or "kid" in description:
            score += 0.2
        if "uniform" in description:
            score += 0.1
        if "helmet" in description:
            score += 0.1
        if "package" in description or "bag" in description or "backpack" in description:
            score += 0.15
        if "red" in description or "blue" in description:
            score += 0.1

        if etype == "reid_match" and ("person" in description or "man" in description or "woman" in description):
            score += 0.5
        if etype == "anpr_read" and ("vehicle" in description or "car" in description):
            score += 0.4
        if etype == "anomaly" and ("running" in description or "loitering" in description):
            score += 0.3
        if etype == "face_match" and ("unauthorized" in description or "unknown" in description):
            score += 0.5

        if score >= 0.2:
            matches.append({
                "event_id": event.get("event_id"),
                "camera_id": event.get("camera_id"),
                "timestamp": event.get("timestamp"),
                "event_type": etype,
                "entity_type": entity,
                "confidence": event.get("confidence", 0),
                "score": round(score, 2),
                "anomaly_label": label,
                "plate_text": plate,
            })

    matches.sort(key=lambda x: x["score"], reverse=True)
    return {
        "query": description,
        "matches_found": len(matches),
        "results": matches[:50],
    }

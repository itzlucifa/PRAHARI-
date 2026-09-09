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
    from .database import SessionLocal, Camera, Event, Alert, init_db, DB_AVAILABLE
except ImportError:
    from database import SessionLocal, Camera, Event, Alert, init_db, DB_AVAILABLE

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


def persist_alert(db, event_id: str, camera_id: str, alert_type: str, confidence: Optional[float]):
    try:
        alert = Alert(
            id=str(uuid.uuid4()),
            event_id=event_id,
            camera_id=camera_id,
            alert_type=alert_type,
            confidence=confidence,
            status="open",
            created_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        )
        db.add(alert)
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.debug("Failed to persist alert: %s", exc)


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
                    alert = dict(item)
                    alert["alert_id"] = str(uuid.uuid4())
                    if db:
                        persist_alert(db, item.get("event_id"), item.get("camera_id"), "detection", item.get("confidence"))
                    for ws in list(alert_subscribers):
                        try:
                            import asyncio
                            asyncio.run(ws.send_json(alert))
                        except Exception:
                            pass
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
                    "status": a.status,
                    "created_at": a.created_at,
                    "acknowledged_by": a.acknowledged_by,
                }
                for a in alerts
            ]
        except Exception as exc:
            logger.error("Failed to fetch alerts: %s", exc)
    return []


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
        elif "alert" in query or "alerts" in query:
            with latest_events_lock:
                alerts = [e for e in latest_events if e.get("confidence", 0) > 0.7]
                reply = f"There are {len(alerts)} high-confidence alert events."
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

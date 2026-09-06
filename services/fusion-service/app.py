from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import os
import json
import uuid
import time
import logging
import threading
from collections import defaultdict
from typing import Optional

import paho.mqtt.client as mqtt
import requests

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct

from shared.events import DetectionEvent, TOPIC_EVENTS, TOPIC_ALERTS

app = FastAPI(title="PRAHARI Fusion Service", version="0.2.0")

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

# In-memory stores
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
        for item in data:
            item["_received_at"] = now
            with latest_events_lock:
                latest_events.append(item)
                if len(latest_events) > MAX_EVENTS:
                    latest_events.pop(0)

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
                for ws in list(alert_subscribers):
                    try:
                        import asyncio
                        asyncio.run(ws.send_json(alert))
                    except Exception:
                        pass
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
    logger.info("Fusion service startup complete")


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/events")
async def get_events(limit: int = 50):
    with latest_events_lock:
        return sorted(latest_events, key=lambda x: x.get("_received_at", 0), reverse=True)[:limit]


@app.post("/events")
async def ingest_event(event: dict):
    now = time.time()
    event["_received_at"] = now
    with latest_events_lock:
        latest_events.append(event)
        if len(latest_events) > MAX_EVENTS:
            latest_events.pop(0)

    if event.get("event_type") == "anpr_read" and event.get("plate_text"):
        plate = event["plate_text"]
        anpr_index[plate].append(event)

    if event.get("event_type") == "detection" and event.get("confidence", 0) > 0.7:
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
async def search_anpr(plate: str):
    return anpr_index.get(plate.upper(), [])


@app.get("/cameras")
async def list_cameras():
    cameras = {}
    with latest_events_lock:
        for e in latest_events:
            cameras[e.get("camera_id")] = {
                "camera_id": e.get("camera_id"),
                "last_seen": e.get("timestamp"),
                "event_type": e.get("event_type"),
            }
    return list(cameras.values())


@app.websocket("/ws/alerts")
async def alerts_ws(websocket: WebSocket):
    await websocket.accept()
    alert_subscribers.append(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        alert_subscribers.remove(websocket)

"""FastAPI API Gateway — exposes event API + subscribes to MQTT bus."""
from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
import asyncio
import json
import os
import threading
import time
import paho.mqtt.client as mqtt
from shared.events import DetectionEvent, TOPIC_EVENTS, TOPIC_ANPR

app = FastAPI(title="PRAHARI API Gateway", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

MQTT_HOST = os.getenv("MQTT_HOST", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", 1883))
QDRANT_PATH = os.getenv("QDRANT_PATH", ":memory:")

recent_events: list[dict] = []
event_queue: asyncio.Queue = asyncio.Queue()
ws_connections: list[WebSocket] = []
_mqtt_connected = False
_main_loop = None

qdrant = QdrantClient(path=QDRANT_PATH)
ANPR_INDEX: dict[str, list[dict]] = {}


def _on_mqtt(client, userdata, msg):
    try:
        data = json.loads(msg.payload.decode())
    except Exception:
        return
    recent_events.append(data)
    if len(recent_events) > 100:
        recent_events.pop(0)
    if data.get("event_type") == "anpr_read" and data.get("plate_text"):
        ANPR_INDEX.setdefault(data["plate_text"], []).append(data)
    if _main_loop is not None:
        asyncio.run_coroutine_threadsafe(event_queue.put(data), _main_loop)
        for ws in list(ws_connections):
            try:
                asyncio.run_coroutine_threadsafe(ws.send_json(data), _main_loop)
            except Exception:
                pass


def _setup_mqtt():
    global _mqtt_connected
    client = mqtt.Client()
    while True:
        try:
            client.connect(MQTT_HOST, MQTT_PORT, 60)
            client.on_message = _on_mqtt
            client.subscribe(TOPIC_EVENTS)
            client.loop_start()
            _mqtt_connected = True
            print(f"[MQTT] Connected to {MQTT_HOST}:{MQTT_PORT}")
            break
        except Exception as e:
            print(f"[MQTT] Connection failed: {e}. Retrying in 3s...")
            time.sleep(3)


@app.on_event("startup")
async def startup():
    global _main_loop
    _main_loop = asyncio.get_event_loop()
    thread = threading.Thread(target=_setup_mqtt, daemon=True)
    thread.start()


@app.get("/health")
async def health():
    return {"status": "ok", "events_seen": len(recent_events), "mqtt_connected": _mqtt_connected}


@app.get("/events")
async def get_events(limit: int = 50):
    return {"events": recent_events[-limit:]}


@app.get("/events/anpr/{plate}")
async def search_anpr(plate: str):
    return ANPR_INDEX.get(plate.upper(), [])


@app.get("/cameras")
async def list_cameras():
    cameras = {}
    for e in recent_events:
        cameras[e.get("camera_id")] = {
            "camera_id": e.get("camera_id"),
            "last_seen": e.get("timestamp"),
            "event_type": e.get("event_type"),
        }
    return list(cameras.values())


@app.websocket("/ws/events")
async def ws_events(ws: WebSocket):
    await ws.accept()
    ws_connections.append(ws)
    try:
        while True:
            data = await event_queue.get()
            await ws.send_json(data)
    except Exception:
        pass
    finally:
        ws_connections.remove(ws)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import os
import json
import logging
import threading
import time
from datetime import datetime, timezone

app = FastAPI(title="PRAHARI ONVIF Discovery", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

logger = logging.getLogger("onvif")

CAMERA_REGISTRY_PATH = os.getenv("CAMERA_REGISTRY_PATH", "config/camera-registry.json")
camera_registry: list[dict] = []
registry_lock = threading.Lock()


def _load_registry():
    global camera_registry
    try:
        with open(CAMERA_REGISTRY_PATH, "r") as f:
            with registry_lock:
                camera_registry = json.load(f)
        logger.info("Loaded %d cameras from registry", len(camera_registry))
    except Exception as e:
        logger.warning("Failed to load camera registry: %s", e)
        camera_registry = []


def _save_registry():
    try:
        with registry_lock:
            with open(CAMERA_REGISTRY_PATH, "w") as f:
                json.dump(camera_registry, f, indent=2)
    except Exception as e:
        logger.warning("Failed to save camera registry: %s", e)


@app.on_event("startup")
def startup():
    _load_registry()


@app.get("/health")
async def health():
    return {"status": "ok", "cameras": len(camera_registry)}


@app.get("/cameras")
def list_cameras():
    with registry_lock:
        return list(camera_registry)


@app.post("/cameras")
def register_camera(camera: dict):
    camera.setdefault("discovered_at", datetime.now(timezone.utc).isoformat())
    with registry_lock:
        for i, existing in enumerate(camera_registry):
            if existing.get("camera_id") == camera.get("camera_id"):
                camera_registry[i] = camera
                _save_registry()
                return camera
        camera_registry.append(camera)
        _save_registry()
    return camera


@app.delete("/cameras/{camera_id}")
def remove_camera(camera_id: str):
    with registry_lock:
        camera_registry = [c for c in camera_registry if c.get("camera_id") != camera_id]
        _save_registry()
    return {"removed": camera_id}

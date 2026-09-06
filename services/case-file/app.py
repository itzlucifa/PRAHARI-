from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import os
import json
import hashlib
import uuid
import time
import logging
import threading
from datetime import datetime, timezone
from typing import Optional

import paho.mqtt.client as mqtt

from shared.events import TOPIC_EVENTS

app = FastAPI(title="PRAHARI Case File Service", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

MQTT_HOST = os.getenv("MQTT_HOST", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", 1883))

logger = logging.getLogger("casefile")

case_files: dict[str, dict] = {}
case_files_lock = threading.Lock()

AUDIT_LOG: list[dict] = []
AUDIT_LOG_LOCK = threading.Lock()
MAX_AUDIT = 1000


def _hash_content(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _audit(action: str, case_id: str, officer: str, details: str = ""):
    entry = {
        "timestamp": _now_iso(),
        "action": action,
        "case_id": case_id,
        "officer": officer,
        "details": details,
    }
    with AUDIT_LOG_LOCK:
        AUDIT_LOG.append(entry)
        if len(AUDIT_LOG) > MAX_AUDIT:
            AUDIT_LOG.pop(0)


@app.post("/case-files")
def create_case_file(officer: str, camera_id: str, description: str = ""):
    case_id = str(uuid.uuid4())
    now = _now_iso()
    case = {
        "case_id": case_id,
        "officer": officer,
        "camera_id": camera_id,
        "description": description,
        "created_at": now,
        "events": [],
        "hash": None,
        "status": "open",
    }
    with case_files_lock:
        case_files[case_id] = case
    _audit("create", case_id, officer, f"camera={camera_id}")
    return case


@app.post("/case-files/{case_id}/events")
def add_event_to_case(case_id: str, event: dict, officer: str):
    with case_files_lock:
        case = case_files.get(case_id)
    if not case:
        return {"error": "Case not found"}
    case["events"].append(event)
    _audit("add_event", case_id, officer, f"event_type={event.get('event_type')}")
    return {"status": "ok", "event_count": len(case["events"])}


@app.post("/case-files/{case_id}/export")
def export_case_file(case_id: str, officer: str):
    with case_files_lock:
        case = case_files.get(case_id)
    if not case:
        return {"error": "Case not found"}
    export_payload = json.dumps(case, indent=2).encode()
    case_hash = _hash_content(export_payload)
    case["hash"] = case_hash
    case["exported_at"] = _now_iso()
    case["status"] = "exported"
    _audit("export", case_id, officer, f"hash={case_hash}")
    return {
        "case_id": case_id,
        "hash": case_hash,
        "event_count": len(case["events"]),
        "exported_at": case["exported_at"],
    }


@app.get("/case-files/{case_id}")
def get_case_file(case_id: str):
    with case_files_lock:
        case = case_files.get(case_id)
    if not case:
        return {"error": "Case not found"}
    return case


@app.get("/case-files/{case_id}/audit")
def get_case_audit(case_id: str):
    return [e for e in AUDIT_LOG if e.get("case_id") == case_id]


@app.get("/health")
async def health():
    return {"status": "ok"}

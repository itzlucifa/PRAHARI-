from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel
import os
import io
import json
import logging
import threading
import cv2
import numpy as np
import base64
from datetime import datetime, timezone

from shared.events import TOPIC_EVENTS

app = FastAPI(title="PRAHARI Privacy Service", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

logger = logging.getLogger("privacy")

AUDIT_LOG: list[dict] = []
AUDIT_LOCK = threading.Lock()
MAX_AUDIT = 1000


class BlurRequest(BaseModel):
    frame_b64: str
    bboxes: list[dict]
    officer: str
    case_id: str = ""


class UnblurRequest(BaseModel):
    frame_b64: str
    original_b64: str
    bboxes: list[dict]
    officer: str
    case_id: str


def _audit(action: str, officer: str, case_id: str = "", details: str = ""):
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "action": action,
        "officer": officer,
        "case_id": case_id,
        "details": details,
    }
    with AUDIT_LOCK:
        AUDIT_LOG.append(entry)
        if len(AUDIT_LOG) > MAX_AUDIT:
            AUDIT_LOG.pop(0)


def _blur_region(frame, bbox):
    h, w = frame.shape[:2]
    x = int(bbox.get("x", 0) * w)
    y = int(bbox.get("y", 0) * h)
    bw = int(bbox.get("w", 0) * w)
    bh = int(bbox.get("h", 0) * h)
    x1, y1 = max(0, x), max(0, y)
    x2, y2 = min(w, x + bw), min(h, y + bh)
    if x2 <= x1 or y2 <= y1:
        return frame
    roi = frame[y1:y2, x1:x2]
    if roi.size == 0:
        return frame
    blurred = cv2.GaussianBlur(roi, (51, 51), 0)
    frame[y1:y2, x1:x2] = blurred
    return frame


@app.post("/blur")
def blur_frame(req: BlurRequest):
    try:
        data = base64.b64decode(req.frame_b64)
        arr = np.frombuffer(data, np.uint8)
        frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if frame is None:
            raise ValueError("Invalid frame")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid frame: {e}")

    blurred_frame = frame.copy()
    for bbox in req.bboxes:
        blurred_frame = _blur_region(blurred_frame, bbox)

    _, buf = cv2.imencode(".jpg", blurred_frame)
    result_b64 = base64.b64encode(buf).decode()

    _audit("blur", req.officer, req.case_id, f"bboxes={len(req.bboxes)}")
    return {"frame_b64": result_b64, "blurred": True}


@app.post("/unblur")
def unblur_frame(req: UnblurRequest):
    if not req.case_id:
        raise HTTPException(status_code=400, detail="case_id required for unblur")
    try:
        orig_data = base64.b64decode(req.original_b64)
        orig_arr = np.frombuffer(orig_data, np.uint8)
        original = cv2.imdecode(orig_arr, cv2.IMREAD_COLOR)
        if original is None:
            raise ValueError("Invalid original frame")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid original frame: {e}")

    result = original.copy()
    _, buf = cv2.imencode(".jpg", result)
    result_b64 = base64.b64encode(buf).decode()

    _audit("unblur", req.officer, req.case_id, f"bboxes={len(req.bboxes)}")
    return {"frame_b64": result_b64, "unblurred": True}


@app.get("/audit")
def get_audit(limit: int = 100):
    with AUDIT_LOCK:
        return AUDIT_LOG[-limit:]


@app.get("/health")
async def health():
    return {"status": "ok"}

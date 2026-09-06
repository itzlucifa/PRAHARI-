"""
Canonical event schema for PRAHARI.
Every adapter publishes events in this exact shape to the MQTT event bus.
Frozen: must not change without updating all adapters + consumers.
"""
from __future__ import annotations
import uuid
from datetime import datetime, timezone
from typing import Literal, Optional
from dataclasses import dataclass, asdict, field
import json


EVENT_TYPES = Literal["detection", "anomaly", "anpr_read", "reid_match", "face_match"]
ENTITY_TYPES = Literal["person", "vehicle", "object"]


@dataclass
class BoundingBox:
    x: float  # normalized [0, 1]
    y: float  # normalized [0, 1]
    w: float  # normalized [0, 1]
    h: float  # normalized [0, 1]


@dataclass
class DetectionEvent:
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    camera_id: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    event_type: EVENT_TYPES = "detection"
    entity_type: ENTITY_TYPES = "person"
    bbox: dict = field(default_factory=lambda: {"x": 0, "y": 0, "w": 0, "h": 0})
    confidence: float = 0.0
    track_id: str = ""
    embedding_id: Optional[str] = None
    plate_text: Optional[str] = None
    anomaly_label: Optional[str] = None
    source_repo: str = ""
    requires_authorization: bool = False

    def to_json(self) -> str:
        return json.dumps(asdict(self))

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "DetectionEvent":
        return cls(**d)


# MQTT topic hierarchy
TOPIC_DETECTIONS = "cameras/+/detections"
TOPIC_EVENTS = "fuse/events/all"
TOPIC_ALERTS = "fuse/alerts/live"
TOPIC_REID = "cameras/+/detections/reid"
TOPIC_ANPR = "cameras/+/detections/anpr"
TOPIC_ANOMALY = "cameras/+/detections/anomaly"
TOPIC_FACE = "cameras/+/detections/face"

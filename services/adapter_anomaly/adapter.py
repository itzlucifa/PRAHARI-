import os
import sys
import time
import logging
import threading
from collections import deque
from datetime import datetime, timezone

import cv2
import numpy as np
import paho.mqtt.client as mqtt

from shared.adapter_base import BaseAdapter
from shared.events import DetectionEvent, TOPIC_EVENTS

logger = logging.getLogger("anomaly-adapter")


class AnomalyAdapter(BaseAdapter):
    def __init__(self, camera_id: str, **kwargs):
        super().__init__(source_repo="anomaly-rules", camera_id=camera_id, **kwargs)
        self._track_history: dict[str, deque] = {}
        self._track_history_lock = threading.Lock()
        self._frame_count = 0
        self._last_anomaly_time: dict[str, float] = {}
        self._anomaly_cooldown = kwargs.get("anomaly_cooldown", 30.0)
        self._loitering_threshold = kwargs.get("loitering_threshold", 120)
        self._crowd_threshold = kwargs.get("crowd_threshold", 5)
        self._motion_threshold = kwargs.get("motion_threshold", 0.15)
        self._prev_gray = None
        self._motion_history = deque(maxlen=30)
        self._last_person_detections: list[dict] = []

    def update_person_detections(self, detections: list[dict]):
        self._last_person_detections = detections

    def _update_track_history(self, track_id: str, bbox: dict, timestamp: float):
        with self._track_history_lock:
            if track_id not in self._track_history:
                self._track_history[track_id] = deque(maxlen=300)
            self._track_history[track_id].append({"bbox": bbox, "timestamp": timestamp})

    def _detect_loitering(self, track_id: str) -> str | None:
        with self._track_history_lock:
            history = list(self._track_history.get(track_id, []))
        if len(history) < self._loitering_threshold:
            return None
        first = history[0]
        last = history[-1]
        dx = abs(last["bbox"]["x"] - first["bbox"]["x"])
        dy = abs(last["bbox"]["y"] - first["bbox"]["y"])
        duration = last["timestamp"] - first["timestamp"]
        if dx < 0.05 and dy < 0.05 and duration > 10:
            return "loitering"
        return None

    def _detect_crowd(self) -> str | None:
        persons = [d for d in self._last_person_detections if d.get("entity_type") == "person"]
        if len(persons) >= self._crowd_threshold:
            return "crowd_forming"
        return None

    def _detect_unusual_movement(self, frame) -> str | None:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (21, 21), 0)
        if self._prev_gray is None:
            self._prev_gray = gray
            return None
        frame_delta = cv2.absdiff(self._prev_gray, gray)
        thresh = cv2.threshold(frame_delta, 25, 255, cv2.THRESH_BINARY)[1]
        motion_ratio = float(np.sum(thresh)) / float(thresh.shape[0] * thresh.shape[1] * 255)
        self._motion_history.append(motion_ratio)
        self._prev_gray = gray
        if len(self._motion_history) < 10:
            return None
        avg_motion = float(np.mean(list(self._motion_history)))
        if avg_motion > self._motion_threshold:
            return "unusual_movement"
        return None

    def _can_emit_anomaly(self, anomaly_type: str, track_id: str) -> bool:
        key = f"{anomaly_type}:{track_id}" if track_id else anomaly_type
        now = time.time()
        last = self._last_anomaly_time.get(key, 0)
        if now - last < self._anomaly_cooldown:
            return False
        self._last_anomaly_time[key] = now
        return True

    def process(self, frame) -> list[DetectionEvent]:
        self._frame_count += 1
        now = time.time()
        events = []
        for det in self._last_person_detections:
            track_id = det.get("track_id", "")
            if track_id:
                self._update_track_history(track_id, det.get("bbox", {}), now)
                anomaly = self._detect_loitering(track_id)
                if anomaly and self._can_emit_anomaly(anomaly, track_id):
                    events.append(
                        self._build_event(
                            event_type="anomaly",
                            entity_type="person",
                            bbox=det.get("bbox", {}),
                            confidence=0.7,
                            track_id=track_id,
                            anomaly_label=anomaly,
                        )
                    )
        crowd_anomaly = self._detect_crowd()
        if crowd_anomaly and self._can_emit_anomaly(crowd_anomaly, ""):
            events.append(
                self._build_event(
                    event_type="anomaly",
                    entity_type="person",
                    bbox={"x": 0, "y": 0, "w": 0, "h": 0},
                    confidence=0.6,
                    track_id="",
                    anomaly_label=crowd_anomaly,
                )
            )
        movement_anomaly = self._detect_unusual_movement(frame)
        if movement_anomaly and self._can_emit_anomaly(movement_anomaly, ""):
            events.append(
                self._build_event(
                    event_type="anomaly",
                    entity_type="object",
                    bbox={"x": 0, "y": 0, "w": 0, "h": 0},
                    confidence=0.5,
                    track_id="",
                    anomaly_label=movement_anomaly,
                )
            )
        return events


def main():
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    camera_id = os.getenv("CAMERA_ID", "camera-01")
    video_source = os.getenv(
        "VIDEO_SOURCE",
        os.path.join(os.path.dirname(__file__), "..", "..", "test_feeds", "camera01.mp4"),
    )
    adapter = AnomalyAdapter(camera_id=camera_id)
    cap = cv2.VideoCapture(video_source)
    if not cap.isOpened():
        logger.error("Cannot open video source: %s", video_source)
        sys.exit(1)
    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                continue
            events = adapter.process(frame)
            if events:
                adapter.publish_batch(events)
                for e in events:
                    logger.info("Anomaly: %s on %s", e.anomaly_label, e.camera_id)
    except KeyboardInterrupt:
        logger.info("Interrupted")
    finally:
        cap.release()


if __name__ == "__main__":
    main()

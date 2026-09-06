import os
import sys
import time
import logging
import threading
import hashlib
from datetime import datetime, timezone

import cv2
import numpy as np
import paho.mqtt.client as mqtt

from shared.adapter_base import BaseAdapter
from shared.events import DetectionEvent, TOPIC_EVENTS

logger = logging.getLogger("face-adapter")

FACE_WATCHLIST = set(os.getenv("FACE_WATCHLIST", "").split(",") if os.getenv("FACE_WATCHLIST") else [])


class FaceAdapter(BaseAdapter):
    def __init__(self, camera_id: str, **kwargs):
        super().__init__(source_repo="insightface", camera_id=camera_id, **kwargs)
        self._use_dummy = False
        self._face_detector = None
        self._recognizer = None
        self._gallery: dict[str, np.ndarray] = {}
        self._gallery_lock = threading.Lock()
        self._last_faces: list[dict] = []

        try:
            self._init_insightface()
        except Exception as exc:
            logger.warning("InsightFace not available (%s), using dummy mode", exc)
            self._use_dummy = True

        self._mqtt.subscribe(TOPIC_EVENTS)
        self._mqtt.message_callback_add(TOPIC_EVENTS, self._on_detection_event)

    def _init_insightface(self):
        try:
            import onnxruntime as ort
            from insightface.app import FaceAnalysis
            providers = ["CPUExecutionProvider"]
            if ort.get_device() == "GPU":
                providers = ["CUDAExecutionProvider", "CPUExecutionProvider"]
            self._face_detector = FaceAnalysis(
                name="buffalo_l",
                providers=providers,
            )
            self._face_detector.prepare(ctx_id=0, det_size=(640, 640))
            self._recognizer = self._face_detector
            logger.info("Initialized InsightFace FaceAnalysis")
        except Exception as exc:
            logger.warning("Failed to init InsightFace: %s", exc)
            raise

    def _on_detection_event(self, client, userdata, msg):
        try:
            import json
            payload = msg.payload.decode()
            data = json.loads(payload)
            if not isinstance(data, list):
                data = [data]
            for item in data:
                if item.get("event_type") == "detection" and item.get("entity_type") == "person":
                    self._last_faces.append(item)
                    if len(self._last_faces) > 20:
                        self._last_faces.pop(0)
        except Exception as exc:
            logger.warning("Failed to parse detection event: %s", exc)

    def _extract_face_embedding(self, frame, person_bbox: dict) -> tuple[np.ndarray | None, dict | None]:
        h, w = frame.shape[:2]
        x = int(person_bbox.get("x", 0) * w)
        y = int(person_bbox.get("y", 0) * h)
        bw = int(person_bbox.get("w", 0) * w)
        bh = int(person_bbox.get("h", 0) * h)
        x1 = max(0, x)
        y1 = max(0, y)
        x2 = min(w, x + bw)
        y2 = min(h, y + bh)

        if x2 <= x1 or y2 <= y1:
            return None, None

        person_crop = frame[y1:y2, x1:x2]
        if person_crop.size == 0:
            return None, None

        if self._use_dummy or self._face_detector is None:
            return np.random.randn(512).astype(np.float32), {"x": x1, "y": y1, "w": x2 - x1, "h": y2 - y1}

        try:
            faces = self._face_detector.get(person_crop)
        except Exception as exc:
            logger.warning("Face detection failed: %s", exc)
            return None, None

        if not faces:
            return None, None

        face = faces[0]
        embedding = face.embedding if hasattr(face, "embedding") else None
        if embedding is None:
            return None, None

        face_bbox = {
            "x": (x1 + face.bbox[0]) / w,
            "y": (y1 + face.bbox[1]) / h,
            "w": (face.bbox[2] - face.bbox[0]) / w,
            "h": (face.bbox[3] - face.bbox[1]) / h,
        }
        return embedding.astype(np.float32), face_bbox

    def _match_watchlist(self, embedding: np.ndarray, threshold: float = 0.6) -> tuple[bool, str | None]:
        if not FACE_WATCHLIST:
            return False, None
        with self._gallery_lock:
            for name, gallery_emb in self._gallery.items():
                similarity = np.dot(embedding, gallery_emb) / (
                    np.linalg.norm(embedding) * np.linalg.norm(gallery_emb) + 1e-8
                )
                if similarity > threshold:
                    return True, name
        return False, None

    def process(self, frame) -> list[DetectionEvent]:
        if not self._last_faces:
            return []

        current = list(self._last_faces)
        self._last_faces.clear()
        events = []

        for person in current:
            bbox = person.get("bbox", {})
            embedding, face_bbox = self._extract_face_embedding(frame, bbox)
            if embedding is None:
                continue

            embedding_id = hashlib.sha256(embedding.tobytes()).hexdigest()[:16]
            matched, watchlist_name = self._match_watchlist(embedding)
            if matched and watchlist_name:
                events.append(
                    self._build_event(
                        event_type="face_match",
                        entity_type="person",
                        bbox=face_bbox or bbox,
                        confidence=0.85,
                        track_id=str(person.get("track_id", "")),
                        embedding_id=embedding_id,
                        requires_authorization=True,
                    )
                )
                logger.info("Face match: %s on %s", watchlist_name, self.camera_id)

        return events

    def add_to_watchlist(self, name: str, embedding: np.ndarray):
        with self._gallery_lock:
            self._gallery[name] = embedding.astype(np.float32)
        logger.info("Added %s to face watchlist", name)


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

    adapter = FaceAdapter(camera_id=camera_id)
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
    except KeyboardInterrupt:
        logger.info("Interrupted")
    finally:
        cap.release()


if __name__ == "__main__":
    main()

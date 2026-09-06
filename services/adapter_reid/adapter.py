import os
import time
import logging
import threading
import cv2
import numpy as np
import paho.mqtt.client as mqtt
import json

try:
    import torch
    from torchreid.reid.utils import FeatureExtractor
    TORCHREID_AVAILABLE = True
except ImportError:
    TORCHREID_AVAILABLE = False
    torch = None

from shared.adapter_base import BaseAdapter
from shared.events import DetectionEvent, TOPIC_EVENTS

logger = logging.getLogger(__name__)


class ReIDAdapter(BaseAdapter):
    def __init__(self, **kwargs):
        super().__init__(source_repo="torchreid", **kwargs)
        self._detections: dict[str, list[dict]] = {}
        self._detections_lock = threading.Lock()
        self._use_dummy = False
        self.extractor = None

        if not TORCHREID_AVAILABLE:
            logger.warning("torchreid not installed. Using dummy embeddings.")
            self._use_dummy = True
        else:
            try:
                self.extractor = FeatureExtractor(
                    model_name="osnet_x0_25",
                    device="cuda" if torch.cuda.is_available() else "cpu",
                )
                logger.info("Initialized torchreid FeatureExtractor (osnet_x0_25)")
            except Exception as exc:
                logger.warning(f"Failed to initialize FeatureExtractor: {exc}. Using dummy embeddings.")
                self._use_dummy = True

        self._mqtt.subscribe(TOPIC_EVENTS)
        self._mqtt.message_callback_add(TOPIC_EVENTS, self._on_mqtt_message)

    def _on_mqtt_message(self, client, userdata, msg):
        try:
            payload = msg.payload.decode()
            data = json.loads(payload)
            if not isinstance(data, list):
                data = [data]
            for item in data:
                if (item.get("event_type") == "detection"
                        and item.get("entity_type") == "person"
                        and item.get("source_repo") != "torchreid"):
                    cam_id = item.get("camera_id", "")
                    with self._detections_lock:
                        self._detections[cam_id] = [item]
        except Exception as exc:
            logger.warning(f"Failed to parse MQTT detection event: {exc}")

    def _crop_persons(self, frame, person_detections):
        h, w = frame.shape[:2]
        crops = []
        bboxes = []
        for det in person_detections:
            bbox = det.get("bbox", {})
            x = int(bbox.get("x", 0) * w)
            y = int(bbox.get("y", 0) * h)
            bw = int(bbox.get("w", 0) * w)
            bh = int(bbox.get("h", 0) * h)
            x1 = max(0, x)
            y1 = max(0, y)
            x2 = min(w, x + bw)
            y2 = min(h, y + bh)
            if x2 > x1 and y2 > y1:
                crops.append(frame[y1:y2, x1:x2])
                bboxes.append(bbox)
        return crops, bboxes

    def _extract_embeddings(self, crops):
        if not crops:
            return []
        if self._use_dummy or self.extractor is None:
            return [np.random.randn(512).astype(np.float32) for _ in crops]
        try:
            return self.extractor(crops)
        except Exception as exc:
            logger.warning(f"Feature extraction failed: {exc}. Falling back to dummy embeddings.")
            return [np.random.randn(512).astype(np.float32) for _ in crops]

    def process(self, frame) -> list[DetectionEvent]:
        with self._detections_lock:
            persons = list(self._detections.get(self.camera_id, []))

        if not persons:
            return []

        crops, bboxes = self._crop_persons(frame, persons)
        if not crops:
            return []

        features = self._extract_embeddings(crops)
        events = []
        for i, feat in enumerate(features):
            if hasattr(feat, "cpu"):
                vec = feat.detach().cpu().numpy().astype(np.float32)
                embedding_id = str(hash(vec.tobytes()))
                vector = vec.tolist()
            else:
                vec = np.asarray(feat, dtype=np.float32)
                embedding_id = str(hash(vec.tobytes()))
                vector = vec.tolist()

            try:
                from qdrant_client import QdrantClient
                from qdrant_client.models import PointStruct
                qdrant = QdrantClient(path=":memory:")
                qdrant.upsert(
                    collection_name="reid_embeddings",
                    points=[
                        PointStruct(
                            id=embedding_id,
                            vector=vector,
                            payload={
                                "camera_id": self.camera_id,
                                "track_id": str(persons[i].get("track_id", "")),
                                "timestamp": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
                            },
                        )
                    ],
                )
            except Exception:
                pass

            events.append(
                self._build_event(
                    event_type="reid_match",
                    entity_type="person",
                    bbox=bboxes[i],
                    confidence=float(persons[i].get("confidence", 1.0)),
                    track_id=str(persons[i].get("track_id", "")),
                    embedding_id=embedding_id,
                )
            )
        return events


def main():
    camera_id = os.getenv("CAMERA_ID", "camera-01")
    video_source = os.getenv(
        "VIDEO_SOURCE",
        "/app/test_feeds/camera01.mp4",
    )

    adapter = ReIDAdapter(camera_id=camera_id)

    cap = cv2.VideoCapture(video_source)
    if not cap.isOpened():
        logger.error(f"Cannot open video source: {video_source}")
        return

    frame_count = 0
    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                logger.info("End of video, looping...")
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                continue

            frame_count += 1
            if frame_count % 10 != 0:
                continue

            events = adapter.process(frame)
            if events:
                adapter.publish_batch(events)
    finally:
        cap.release()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()

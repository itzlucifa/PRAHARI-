import os
import sys
import time
import cv2
import logging
from shared.adapter_base import BaseAdapter, DummyAdapter
from shared.events import DetectionEvent, TOPIC_EVENTS

logger = logging.getLogger(__name__)

VIDEO_SOURCE = os.getenv(
    "VIDEO_SOURCE",
    "/app/test_feeds/camera01.mp4",
)
CAMERA_ID = os.getenv("CAMERA_ID", "camera-01")
TARGET_FPS = float(os.getenv("TARGET_FPS", "3.0"))
FRAME_INTERVAL = 1.0 / TARGET_FPS


def _load_yolo():
    try:
        from ultralytics import YOLO
        return YOLO("yolov8n.pt")
    except Exception as exc:
        logger.warning("ultralytics not available (%s), falling back to DummyAdapter", exc)
        return None


class DetectionAdapter(BaseAdapter):
    def __init__(self, **kwargs):
        super().__init__(source_repo="ultralytics", **kwargs)
        self.model = _load_yolo()

    def process(self, frame) -> list[DetectionEvent]:
        if self.model is None:
            adapter = DummyAdapter(camera_id=self.camera_id, mqtt_host=self.mqtt_host, mqtt_port=self.mqtt_port)
            return adapter.process(frame)

        results = self.model(frame, verbose=False)[0]
        events = []
        for box in results.boxes:
            cls = int(box.cls[0])
            conf = float(box.conf[0])
            label = results.names[cls]
            x1, y1, x2, y2 = map(float, box.xyxy[0])
            h, w = frame.shape[:2]
            bbox = {
                "x": x1 / w,
                "y": y1 / h,
                "w": (x2 - x1) / w,
                "h": (y2 - y1) / h,
            }
            entity = "person" if label == "person" else "object"
            events.append(
                self._build_event(
                    event_type="detection",
                    entity_type=entity,
                    bbox=bbox,
                    confidence=conf,
                    track_id=str(box.id[0]) if box.id is not None else "",
                )
            )
        return events


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    camera_id = CAMERA_ID
    adapter = DetectionAdapter(camera_id=camera_id)

    if not os.path.exists(VIDEO_SOURCE):
        logger.error("Video source not found: %s", VIDEO_SOURCE)
        sys.exit(1)

    cap = cv2.VideoCapture(VIDEO_SOURCE)
    if not cap.isOpened():
        logger.error("Failed to open video source: %s", VIDEO_SOURCE)
        sys.exit(1)

    try:
        while True:
            start = time.time()
            ret, frame = cap.read()
            if not ret:
                logger.info("End of stream, restarting")
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                continue

            events = adapter.process(frame)
            adapter.publish_batch(events)

            for event in events:
                logger.info("Published event_type=%s camera_id=%s", event.event_type, event.camera_id)

            elapsed = time.time() - start
            sleep_for = FRAME_INTERVAL - elapsed
            if sleep_for > 0:
                time.sleep(sleep_for)
    finally:
        cap.release()


if __name__ == "__main__":
    main()

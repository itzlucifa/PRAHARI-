import os
import re
import sys
import time
import logging
import cv2
import numpy as np
import paho.mqtt.client as mqtt

from shared.adapter_base import BaseAdapter
from shared.events import DetectionEvent, TOPIC_EVENTS


ANPR_PATTERN = re.compile(r"[A-Z]{2}[0-9]{1,2}[A-Z]{0,2}[0-9]{1,4}")
INDIAN_CHAR_MAP = {"O": "0", "I": "1", "Z": "2", "B": "8", "G": "6", "S": "5"}
VEHICLE_CLASSES = {"car", "truck", "bus", "motorcycle"}

log = logging.getLogger("anpr-adapter")


def _try_import_heavy():
    try:
        import easyocr  # type: ignore
    except Exception as e:
        log.warning("easyocr not available: %s", e)
        easyocr = None
    try:
        from ultralytics import YOLO  # type: ignore
    except Exception as e:
        log.warning("ultralytics not available: %s", e)
        YOLO = None
    return easyocr, YOLO


easyocr, YOLO = _try_import_heavy()


class ANPRAdapter(BaseAdapter):
    def __init__(self, camera_id: str, frame_stride: int = 5, **kwargs):
        super().__init__(source_repo="anpr", camera_id=camera_id, **kwargs)
        self.frame_stride = max(1, int(frame_stride))
        self.detector = None
        self.reader = None
        self._disabled = False

        if YOLO is None or easyocr is None:
            log.warning("ANPR disabled: missing ultralytics or easyocr")
            self._disabled = True
            return

        try:
            self.detector = YOLO("yolov8n.pt")
        except Exception as e:
            log.warning("Failed to load YOLOv8 model: %s", e)
            self._disabled = True
            return

        try:
            self.reader = easyocr.Reader(["en"], gpu=False)
        except Exception as e:
            log.warning("Failed to init EasyOCR reader: %s", e)
            self._disabled = True

    def _correct_plate(self, text: str) -> str:
        corrected = []
        for i, ch in enumerate(text):
            if ch in INDIAN_CHAR_MAP:
                corrected.append(INDIAN_CHAR_MAP[ch])
            else:
                corrected.append(ch)
        return "".join(corrected)

    def _focus_score(self, crop: np.ndarray) -> float:
        if crop is None or crop.size == 0:
            return 0.0
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        return float(cv2.Laplacian(gray, cv2.CV_64F).var())

    def _read_plate(self, plate_img: np.ndarray) -> tuple[str | None, float]:
        if self.reader is None or plate_img is None or plate_img.size == 0:
            return None, 0.0
        try:
            results = self.reader.readtext(plate_img, detail=0, paragraph=True)
        except Exception as e:
            log.warning("OCR failed: %s", e)
            return None, 0.0
        if not results:
            return None, 0.0
        text = results[0].upper().replace(" ", "")
        corrected = self._correct_plate(text)
        if ANPR_PATTERN.match(corrected):
            return corrected, self._focus_score(plate_img)
        return None, 0.0

    def process(self, frame) -> list[DetectionEvent]:
        if self._disabled or self.detector is None or frame is None:
            return []
        try:
            results = self.detector(frame, verbose=False)[0]
        except Exception as e:
            log.warning("YOLO inference failed: %s", e)
            return []

        events: list[DetectionEvent] = []
        h, w = frame.shape[:2]
        car_candidates: dict[str, dict] = {}

        for box in results.boxes:
            cls = int(box.cls[0])
            label = results.names.get(cls, "")
            if label not in VEHICLE_CLASSES:
                continue
            x1, y1, x2, y2 = map(int, box.xyxy[0])
            x1c, y1c = max(0, x1), max(0, y1)
            x2c, y2c = min(w, x2), min(h, y2)
            if x2c <= x1c or y2c <= y1c:
                continue
            vehicle_crop = frame[y1c:y2c, x1c:x2c]
            plate_text, focus = self._read_plate(vehicle_crop)
            track_id = str(int(box.id[0])) if box.id is not None else ""
            conf = float(box.conf[0])
            score = (1.0 if plate_text else 0.0) + 0.15 * conf + 0.10 * min(focus / 100.0, 1.0)

            if track_id not in car_candidates or score > car_candidates[track_id]["score"]:
                car_candidates[track_id] = {
                    "event": self._build_event(
                        event_type="anpr_read",
                        entity_type="vehicle",
                        bbox={"x": x1 / w, "y": y1 / h, "w": (x2 - x1) / w, "h": (y2 - y1) / h},
                        confidence=conf,
                        track_id=track_id,
                        plate_text=plate_text,
                    ),
                    "score": score,
                }

        events = [v["event"] for v in car_candidates.values()]
        return events


def main():
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    camera_id = os.getenv("CAMERA_ID", "camera-01")
    video_source = os.getenv(
        "VIDEO_SOURCE",
        "/app/test_feeds/camera01.mp4",
    )
    try:
        frame_stride = int(os.getenv("FRAME_STRIDE", "5"))
    except ValueError:
        frame_stride = 5

    adapter = ANPRAdapter(camera_id=camera_id, frame_stride=frame_stride)

    if adapter._disabled:
        log.error("ANPR adapter running in disabled mode (no detections will be emitted)")

    cap = cv2.VideoCapture(video_source)
    if not cap.isOpened():
        log.error("Failed to open video source: %s", video_source)
        sys.exit(1)

    log.info(
        "ANPR adapter started | camera_id=%s source=%s stride=%d",
        camera_id,
        video_source,
        frame_stride,
    )

    frame_idx = 0
    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                log.info("End of stream or read failure; restarting")
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                continue
            if frame_idx % frame_stride == 0:
                events = adapter.process(frame)
                if events:
                    adapter.publish_batch(events)
            frame_idx += 1
    except KeyboardInterrupt:
        log.info("Interrupted by user")
    finally:
        cap.release()


if __name__ == "__main__":
    main()

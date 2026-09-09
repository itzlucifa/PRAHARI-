from shared.adapter_base import BaseAdapter

try:
    from ultralytics import YOLO
    import torch
    ULTRALYTICS_AVAILABLE = True
except ImportError:
    ULTRALYTICS_AVAILABLE = False

try:
    import easyocr
    EASYOCR_AVAILABLE = True
except ImportError:
    EASYOCR_AVAILABLE = False

import cv2
import numpy as np
import time
import re
import logging
from typing import Optional

logger = logging.getLogger("adapter_anpr")


class ANPRAdapter(BaseAdapter):
    def __init__(self, camera_id: str = "camera-01", video_source: str = "0"):
        super().__init__(camera_id, video_source)
        self.model = None
        self.reader = None
        if ULTRALYTICS_AVAILABLE:
            try:
                self.model = YOLO("yolov8n.pt")
            except Exception as exc:
                logger.warning("YOLO init failed: %s", exc)
        if EASYOCR_AVAILABLE:
            try:
                self.reader = easyocr.Reader(["en"], gpu=False)
            except Exception as exc:
                logger.warning("EasyOCR init failed: %s", exc)
        self.plate_pattern = re.compile(r"[A-Z]{2,3}\s*\d{1,2}\s*[A-Z]{1,3}\s*\d{1,4}")

    def process(self, frame):
        results = []
        try:
            if self.model:
                yolo_results = self.model(frame, verbose=False, conf=0.4)
                for r in yolo_results:
                    for box in r.boxes:
                        x1, y1, x2, y2 = map(int, box.xyxy[0])
                        plate_crop = frame[y1:y2, x1:x2]
                        text = self._ocr_plate(plate_crop)
                        if text:
                            results.append({
                                "event_type": "anpr_read",
                                "entity_type": "vehicle",
                                "bbox": {
                                    "x": x1 / frame.shape[1],
                                    "y": y1 / frame.shape[0],
                                    "w": (x2 - x1) / frame.shape[1],
                                    "h": (y2 - y1) / frame.shape[0],
                                },
                                "confidence": float(box.conf[0]),
                                "track_id": f"anpr_{int(time.time()*1000)}",
                                "plate_text": text,
                                "source_repo": "indian-anpr",
                            })
        except Exception as exc:
            logger.debug("ANPR processing error: %s", exc)
        return results

    def _ocr_plate(self, image) -> Optional[str]:
        try:
            if image.size == 0:
                return None
            if self.reader:
                ocr_results = self.reader.readtext(image, paragraph=False)
                for _, text, conf in ocr_results:
                    if conf > 0.5:
                        candidate = text.upper().replace(" ", "")
                        if self.plate_pattern.match(candidate) or len(candidate) >= 6:
                            return candidate
            return None
        except Exception:
            return None
import os
import sys
import time
import cv2
import numpy as np
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

MODEL_PATH = os.getenv(
    "DETECTION_MODEL_PATH",
    os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "models", "yolov8n.onnx"),
)

COCO_CLASSES = {
    0: "person", 1: "bicycle", 2: "car", 3: "motorcycle", 4: "airplane",
    5: "bus", 6: "train", 7: "truck", 8: "boat", 9: "traffic light",
    10: "fire hydrant", 11: "stop sign", 12: "parking meter", 13: "bench",
    14: "bird", 15: "cat", 16: "dog", 17: "horse", 18: "sheep", 19: "cow",
    20: "elephant", 21: "bear", 22: "zebra", 23: "giraffe", 24: "backpack",
    25: "umbrella", 26: "handbag", 27: "tie", 28: "suitcase", 29: "frisbee",
    30: "skis", 31: "snowboard", 32: "sports ball", 33: "kite", 34: "baseball bat",
    35: "baseball glove", 36: "skateboard", 37: "surfboard", 38: "tennis racket", 39: "bottle",
    40: "wine glass", 41: "cup", 42: "fork", 43: "knife", 44: "spoon",
    45: "bowl", 46: "banana", 47: "apple", 48: "sandwich", 49: "orange",
    50: "broccoli", 51: "pizza", 52: "hot dog", 53: "donut", 54: "cake",
    55: "chair", 56: "couch", 57: "potted plant", 58: "bed", 59: "dining table",
    60: "toilet", 61: "tv", 62: "laptop", 63: "mouse", 64: "remote",
    65: "keyboard", 66: "cell phone", 67: "microwave", 68: "oven", 69: "toaster",
    70: "sink", 71: "refrigerator", 72: "book", 73: "clock", 74: "vase",
    75: "scissors", 76: "teddy bear", 77: "hair drier", 78: "toothbrush",
}


def _get_optimal_provider():
    """Detect optimal ONNX Runtime provider based on hardware."""
    try:
        import onnxruntime as ort
        available = ort.get_available_providers()
        priority = ['CUDAExecutionProvider', 'CoreMLExecutionProvider', 'OpenVINOExecutionProvider', 'CPUExecutionProvider']
        for p in priority:
            if p in available:
                logger.info("Using ONNX provider: %s", p)
                return p
        logger.warning("No hardware accelerator found, using CPU")
        return 'CPUExecutionProvider'
    except ImportError:
        return None


def _load_onnx_model():
    """Load ONNX model with optimal provider. Returns (session, input_name, output_name) or None."""
    if not os.path.exists(MODEL_PATH):
        logger.info("ONNX model not found at %s, using PyTorch fallback", MODEL_PATH)
        return None

    try:
        import onnxruntime as ort

        provider = _get_optimal_provider()
        if provider is None:
            return None

        sess_options = ort.SessionOptions()
        sess_options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL

        session = ort.InferenceSession(MODEL_PATH, sess_options, providers=[provider])
        input_name = session.get_inputs()[0].name
        output_name = session.get_outputs()[0].name

        logger.info("ONNX model loaded: %s (provider: %s)", MODEL_PATH, provider)
        return (session, input_name, output_name)
    except ImportError:
        logger.info("onnxruntime not installed, using PyTorch fallback")
        return None
    except Exception as exc:
        logger.warning("ONNX model load failed (%s), using PyTorch fallback", exc)
        return None


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
        self.onnx_session = _load_onnx_model()
        self.model = _load_yolo() if self.onnx_session is None else None

    def process(self, frame) -> list[DetectionEvent]:
        if self.onnx_session is not None:
            return self._process_onnx(frame)
        elif self.model is not None:
            return self._process_torch(frame)
        else:
            adapter = DummyAdapter(camera_id=self.camera_id, mqtt_host=self.mqtt_host, mqtt_port=self.mqtt_port)
            return adapter.process(frame)

    def _process_onnx(self, frame) -> list[DetectionEvent]:
        session, input_name, output_name = self.onnx_session
        h, w = frame.shape[:2]

        img = cv2.resize(frame, (640, 640))
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        img = img.astype(np.float32) / 255.0
        img[0] = (img[0] - 0.485) / 0.229
        img[1] = (img[1] - 0.456) / 0.224
        img[2] = (img[2] - 0.406) / 0.225
        img = np.transpose(img, (2, 0, 1))
        img = np.expand_dims(img, axis=0)

        outputs = session.run(None, {input_name: img})
        predictions = outputs[0]

        events = []
        for pred in predictions[0]:
            x1, y1, x2, y2 = pred[0], pred[1], pred[2], pred[3]
            conf = float(pred[4])
            cls_scores = pred[5:]
            cls_id = int(np.argmax(cls_scores))
            class_conf = float(cls_scores[cls_id]) * conf

            if class_conf > 0.25:
                label = COCO_CLASSES.get(cls_id, "object")
                entity = "person" if label == "person" else "object"
                bbox = {
                    "x": x1 / w,
                    "y": y1 / h,
                    "w": (x2 - x1) / w,
                    "h": (y2 - y1) / h,
                }
                events.append(
                    self._build_event(
                        event_type="detection",
                        entity_type=entity,
                        bbox=bbox,
                        confidence=class_conf,
                        track_id="",
                    )
                )
        return events

    def _process_torch(self, frame) -> list[DetectionEvent]:
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

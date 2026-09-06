"""
PRAHARI Live Demo
=================
Unified real-time YOLOv8 demo. Use --source to pick a webcam index or a video file.
"""
import os
import sys
import time
import cv2
import json
import urllib.request
import argparse
from datetime import datetime, timezone
from http.server import HTTPServer, BaseHTTPRequestHandler
from threading import Thread

FUSION_URL = os.getenv("FUSION_URL", "http://localhost:8000/events")
CAMERA_ID = os.getenv("CAMERA_ID", "camera-01")
SOURCE_REPO = "ultralytics"
VIEWER_PORT = int(os.getenv("VIEWER_PORT", "8080"))
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRAME_OUTPUT = os.path.join(PROJECT_ROOT, "demo_frames", "latest_annotated.jpg")

os.makedirs(os.path.dirname(FRAME_OUTPUT), exist_ok=True)

print("=" * 60)
print("PRAHARI LIVE DEMO")
print("=" * 60)

# Load YOLO
try:
    from ultralytics import YOLO
    print("[DEMO] Loading YOLOv8...")
    model = YOLO(os.path.join(PROJECT_ROOT, "models", "yolov8n.pt"))
    print("[DEMO] YOLOv8 loaded!")
except Exception as e:
    print(f"[DEMO] YOLO failed: {e}")
    model = None

# Parse source
parser = argparse.ArgumentParser(description="PRAHARI Live Demo")
parser.add_argument("--source", default="0", help="Video source (0 = webcam, or path to video file)")
args = parser.parse_args()

if args.source.isdigit():
    video_source = int(args.source)
else:
    video_source = args.source

cap = cv2.VideoCapture(video_source)
if not cap.isOpened():
    print(f"[DEMO] ERROR: Cannot open video source: {video_source}")
    sys.exit(1)

print(f"[DEMO] Source: {video_source}")
print(f"[DEMO] Frame viewer: http://localhost:{VIEWER_PORT}")
print("=" * 60)
print()

frame_count = 0
detection_count = 0
start_time = time.time()

TARGET_CLASSES = {0: "person", 2: "car", 3: "motorcycle", 5: "bus", 7: "truck"}


def publish_event(event):
    try:
        data = json.dumps(event).encode("utf-8")
        req = urllib.request.Request(
            FUSION_URL,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=1) as resp:
            return resp.status == 200
    except Exception:
        return False


class FrameHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in ('/', '/frame'):
            try:
                with open(FRAME_OUTPUT, 'rb') as f:
                    data = f.read()
                self.send_response(200)
                self.send_header('Content-type', 'image/jpeg')
                self.end_headers()
                self.wfile.write(data)
            except Exception:
                self.send_response(404)
                self.end_headers()
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass


def start_viewer():
    server = HTTPServer(('0.0.0.0', VIEWER_PORT), FrameHandler)
    server.serve_forever()


Thread(target=start_viewer, daemon=True).start()
print(f"[DEMO] Frame viewer started at http://localhost:{VIEWER_PORT}")
print()

try:
    while True:
        ret, frame = cap.read()
        if not ret:
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            continue

        frame_count += 1
        annotated = frame.copy()
        h, w = frame.shape[:2]
        detections = []

        if model:
            results = model(frame, verbose=False, conf=0.4)[0]
            for box in results.boxes:
                cls = int(box.cls[0])
                conf = float(box.conf[0])
                if cls not in TARGET_CLASSES:
                    continue
                label = TARGET_CLASSES[cls]
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                if cls == 0:
                    color = (0, 255, 0)
                elif cls in [2, 5, 7]:
                    color = (255, 0, 0)
                else:
                    color = (0, 255, 255)
                cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)
                cv2.putText(annotated, f"{label} {conf:.2f}", (x1, y1 - 10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
                detections.append({
                    "label": label,
                    "conf": conf,
                    "norm_bbox": {
                        "x": round(x1 / w, 3),
                        "y": round(y1 / h, 3),
                        "w": round((x2 - x1) / w, 3),
                        "h": round((y2 - y1) / h, 3),
                    }
                })

        if frame_count % 20 == 0 and detections:
            for det in detections[:3]:
                detection_count += 1
                event = {
                    "event_id": f"live-{frame_count:06d}",
                    "camera_id": CAMERA_ID,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "event_type": "detection",
                    "entity_type": det["label"],
                    "bbox": det["norm_bbox"],
                    "confidence": det["conf"],
                    "track_id": f"track_{frame_count}",
                    "source_repo": SOURCE_REPO,
                    "requires_authorization": False,
                }
                publish_event(event)

        elapsed = time.time() - start_time
        fps = frame_count / elapsed if elapsed > 0 else 0
        cv2.putText(annotated, f"FPS: {fps:.1f}", (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
        cv2.putText(annotated, f"Detections: {detection_count}", (10, 60),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
        cv2.putText(annotated, f"Frame: {frame_count}", (10, 90),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
        cv2.imwrite(FRAME_OUTPUT, annotated)

        if frame_count % 30 == 0:
            print(f"[DEMO] Frame {frame_count} | FPS: {fps:.1f} | Detections: {detection_count}")
            for d in detections:
                print(f"  -> {d['label']} {d['conf']:.2f}")

except KeyboardInterrupt:
    print("\n[DEMO] Stopped")

finally:
    cap.release()
    print(f"\n[DONE] Total detections: {detection_count}")
    print(f"[DONE] Viewer: http://localhost:{VIEWER_PORT}")
    print(f"[DONE] Frame: {FRAME_OUTPUT}")

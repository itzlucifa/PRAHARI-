import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.adapter_detection.adapter import _load_yolo
import cv2

model = _load_yolo()
print("Model loaded:", model is not None)
if model:
    feed_path = os.path.join(os.path.dirname(__file__), "..", "test_feeds", "camera01.mp4")
    cap = cv2.VideoCapture(feed_path)
    ret, frame = cap.read()
    cap.release()
    print("Frame shape:", frame.shape if ret and frame is not None else "None")
    if ret and frame is not None:
        results = model(frame, verbose=False)[0]
        print("Detections:", len(results.boxes))
        for box in results.boxes:
            cls = int(box.cls[0])
            conf = float(box.conf[0])
            label = results.names[cls]
            print(f"  {label}: {conf:.2f}")

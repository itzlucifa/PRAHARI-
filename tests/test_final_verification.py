import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import time
import json
import urllib.request
import urllib.error
import cv2
import numpy as np

from services.adapter_detection.adapter import DetectionAdapter
from services.adapter_anpr.adapter import ANPRAdapter
from services.adapter_reid.adapter import ReIDAdapter
from services.adapter_anomaly.adapter import AnomalyAdapter

print("Final Verification")

# 1. Detection
frame = None
feed_path = os.path.join(os.path.dirname(__file__), "..", "test_feeds", "camera01.mp4")
if os.path.exists(feed_path):
    cap = cv2.VideoCapture(feed_path)
    ret, frame = cap.read()
    cap.release()
    if not ret:
        frame = None

if frame is None:
    frame = np.zeros((480, 640, 3), dtype=np.uint8)

det = DetectionAdapter(camera_id="camera-01", mqtt_host="127.0.0.1")
det_events = det.process(frame)
print(f"1. Detection: {len(det_events)} events")

# 2. ANPR
anpr = ANPRAdapter(camera_id="camera-01", mqtt_host="127.0.0.1")
anpr_events = anpr.process(frame)
print(f"2. ANPR: {len(anpr_events)} events")

# 3. ReID
reid = ReIDAdapter(camera_id="camera-01", mqtt_host="127.0.0.1")
reid.publish_batch(det_events)
time.sleep(1)
reid_events = reid.process(frame)
print(f"3. ReID: {len(reid_events)} events")

# 4. Anomaly
anomaly = AnomalyAdapter(camera_id="camera-01", mqtt_host="127.0.0.1")
for _ in range(5):
    anomaly.process(frame)
anomaly_events = anomaly.process(frame)
print(f"4. Anomaly: {len(anomaly_events)} events")

# 5. API gateway health
time.sleep(2)
try:
    req = urllib.request.Request("http://localhost:8000/health")
    with urllib.request.urlopen(req) as resp:
        health = json.loads(resp.read())
    print(f"5. API gateway health: {health}")
except Exception as e:
    print(f"5. API gateway: ERROR {e}")

# 6. Fusion events
try:
    req = urllib.request.Request("http://localhost:8000/events?limit=10")
    with urllib.request.urlopen(req) as resp:
        result = json.loads(resp.read())
    event_list = result.get("events", result) if isinstance(result, dict) else result
    print(f"6. Fusion events: {len(event_list)} total")
except Exception as e:
    print(f"6. Fusion events: ERROR {e}")

# 7. Cameras
try:
    req = urllib.request.Request("http://localhost:8000/cameras")
    with urllib.request.urlopen(req) as resp:
        cameras = json.loads(resp.read())
    if isinstance(cameras, dict):
        cameras = cameras.get("cameras", [])
    print(f"7. Cameras: {len(cameras)} registered")
except Exception as e:
    print(f"7. Cameras: ERROR {e}")

print("Verification complete")

import sys
import os
import time
import threading
import json
import urllib.request
import urllib.error
import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(__file__))

from services.adapter_detection.adapter import DetectionAdapter
from services.adapter_anpr.adapter import ANPRAdapter
from services.adapter_reid.adapter import ReIDAdapter
from services.adapter_anomaly.adapter import AnomalyAdapter

VIDEO_SOURCE = os.path.join(os.path.dirname(__file__), "test_feeds", "camera01.mp4")
API_URL = "http://localhost:8000"
MQTT_BROKER_NEEDED = False

if MQTT_BROKER_NEEDED:
    from amqtt.broker import Broker
    import asyncio

    config = {
        'listeners': {'default': {'type': 'tcp', 'bind': '127.0.0.1:1883'}},
        'sys_interval': 0,
        'auth': {'allow-anonymous': True},
        'topic-check': {'enabled': False},
    }
    async def run_broker():
        broker = Broker(config)
        await broker.start()
        await asyncio.sleep(60)
    broker_thread = threading.Thread(target=asyncio.run, args=(run_broker(),), daemon=True)
    broker_thread.start()
    time.sleep(3)

cap = cv2.VideoCapture(VIDEO_SOURCE)
if not cap.isOpened():
    print("ERROR: Cannot open video source")
    sys.exit(1)

det = DetectionAdapter(camera_id="camera-01", mqtt_host="127.0.0.1")
anpr = ANPRAdapter(camera_id="camera-01", mqtt_host="127.0.0.1")
reid = ReIDAdapter(camera_id="camera-01", mqtt_host="127.0.0.1")
anomaly = AnomalyAdapter(camera_id="camera-01", mqtt_host="127.0.0.1")

print("=== LIVE DEMO RUNNING ===")
print(f"Video: {VIDEO_SOURCE}")
print(f"Dashboard: http://localhost:5173")
print(f"API: {API_URL}")
print("Press Ctrl+C to stop\n")

frame_idx = 0
try:
    while True:
        ret, frame = cap.read()
        if not ret:
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            continue

        frame_idx += 1

        det_events = det.process(frame)
        det.publish_batch(det_events)

        if frame_idx % 5 == 0:
            anpr_events = anpr.process(frame)
            anpr.publish_batch(anpr_events)

        if frame_idx % 3 == 0:
            reid.publish_batch(det_events)
            reid_events = reid.process(frame)
            reid.publish_batch(reid_events)

        anomaly_events = anomaly.process(frame)
        if anomaly_events:
            anomaly.publish_batch(anomaly_events)

        if frame_idx % 30 == 0:
            try:
                req = urllib.request.Request(f"{API_URL}/health")
                with urllib.request.urlopen(req, timeout=2) as resp:
                    health = json.loads(resp.read())
                print(f"[{frame_idx}] health={health.get('status')} events_seen={health.get('events_seen', '?')}")
            except Exception:
                pass

        time.sleep(0.1)
except KeyboardInterrupt:
    print("\nDemo stopped")
finally:
    cap.release()

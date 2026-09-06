import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import time
import json
import urllib.request
import urllib.error
import numpy as np
import paho.mqtt.client as mqtt
import cv2
from amqtt.broker import Broker
import asyncio
import threading

# Start MQTT broker
config = {'listeners': {'default': {'type': 'tcp', 'bind': '127.0.0.1:1883'}}, 'sys_interval': 0, 'auth': {'allow-anonymous': True}, 'topic-check': {'enabled': False}}
async def run_broker():
    broker = Broker(config)
    await broker.start()
    await asyncio.sleep(25)
broker_thread = threading.Thread(target=asyncio.run, args=(run_broker(),), daemon=True)
broker_thread.start()
time.sleep(3)

# Start all adapters in background threads
from services.adapter_detection.adapter import DetectionAdapter
from services.adapter_anpr.adapter import ANPRAdapter
from services.adapter_reid.adapter import ReIDAdapter

url = "https://ultralytics.com/images/bus.jpg"
urllib.request.urlretrieve(url, "test_bus.jpg")
frame = cv2.imread("test_bus.jpg")

det = DetectionAdapter(camera_id="camera-01", mqtt_host="127.0.0.1")
anpr = ANPRAdapter(camera_id="camera-01", mqtt_host="127.0.0.1")
reid = ReIDAdapter(camera_id="camera-01", mqtt_host="127.0.0.1")

# Publish a detection event first so ReID has person detections to crop
det_events = det.process(frame)
det.publish_batch(det_events)
time.sleep(1)

anpr_events = anpr.process(frame)
anpr.publish_batch(anpr_events)
time.sleep(1)

reid_events = reid.process(frame)
reid.publish_batch(reid_events)
time.sleep(2)

# Check fusion service
req = urllib.request.Request("http://localhost:8000/events?limit=20")
with urllib.request.urlopen(req) as resp:
    result = json.loads(resp.read())
events = result.get("events", result) if isinstance(result, dict) else result

types = [e["event_type"] for e in events]
print(f"Total events in fusion service: {len(events)}")
print(f"Event types: { {t: types.count(t) for t in set(types)} }")

# Check ANPR index (dummy adapter generates random plates, so check if any exist)
req2 = urllib.request.Request("http://localhost:8000/events/anpr/MH04XY9999")
try:
    with urllib.request.urlopen(req2) as resp:
        anpr_results = json.loads(resp.read())
    print(f"ANPR search for MH04XY9999: {len(anpr_results)} results")
except urllib.error.HTTPError:
    print("ANPR search: no results for dummy plate (expected)")

# Check cameras
req3 = urllib.request.Request("http://localhost:8000/cameras")
with urllib.request.urlopen(req3) as resp:
    cameras = json.loads(resp.read())
if isinstance(cameras, dict):
    cameras = cameras.get("cameras", cameras)
print(f"Cameras registered: {len(cameras)}")

assert len(events) > 0, "No events in fusion service"
assert "detection" in types, "No detection events"
assert "anpr_read" in types, "No ANPR events"
assert "reid_match" in types, "No ReID events"

os.remove("test_bus.jpg")
print("END-TO-END PIPELINE TEST: ALL PASSED")

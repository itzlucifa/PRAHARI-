import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import cv2
import urllib.request
import numpy as np
from amqtt.broker import Broker
import asyncio
import threading
import time
import json

import paho.mqtt.client as mqtt

# Start MQTT broker
config = {'listeners': {'default': {'type': 'tcp', 'bind': '127.0.0.1:1883'}}, 'sys_interval': 0, 'auth': {'allow-anonymous': True}, 'topic-check': {'enabled': False}}
async def run_broker():
    broker = Broker(config)
    await broker.start()
    await asyncio.sleep(30)
broker_thread = threading.Thread(target=asyncio.run, args=(run_broker(),), daemon=True)
broker_thread.start()
time.sleep(3)

# Test 1: Detection adapter with real image
from services.adapter_detection.adapter import DetectionAdapter
url = "https://ultralytics.com/images/bus.jpg"
urllib.request.urlretrieve(url, "test_bus.jpg")
frame = cv2.imread("test_bus.jpg")
adapter = DetectionAdapter(camera_id="test-cam", mqtt_host="127.0.0.1")
events = adapter.process(frame)
assert len(events) > 0, "No detections from YOLO"
print(f"1. Detection adapter: PASS ({len(events)} detections)")

# Test 2: ANPR adapter import
from services.adapter_anpr.adapter import ANPRAdapter
anpr = ANPRAdapter(camera_id="test-cam", mqtt_host="127.0.0.1")
print(f"2. ANPR adapter: PASS (disabled={anpr._disabled})")

# Test 3: ReID adapter import
from services.adapter_reid.adapter import ReIDAdapter
reid = ReIDAdapter(camera_id="test-cam", mqtt_host="127.0.0.1")
print(f"3. ReID adapter: PASS (use_dummy={reid._use_dummy})")

# Test 4: MQTT publish
received = []
def on_msg(client, userdata, msg):
    received.append(json.loads(msg.payload.decode()))
sub = mqtt.Client()
sub.on_message = on_msg
sub.connect('127.0.0.1', 1883, 60)
sub.subscribe('fuse/events/all')
sub.loop_start()
time.sleep(1)

for e in events:
    adapter.publish(e)
time.sleep(2)
assert len(received) > 0, "No events received via MQTT"
print(f"4. MQTT publish: PASS ({len(received)} events)")

# Cleanup
os.remove("test_bus.jpg")
print("PHASE 3 TEST: ALL PASSED")

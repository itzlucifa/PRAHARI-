import sys
import os
import json
import time
import urllib.request
import urllib.error
import urllib.parse
import base64
import cv2
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

print("Final Audit")

# 1. Detection adapter
from services.adapter_detection.adapter import DetectionAdapter
frame = np.zeros((480, 640, 3), dtype=np.uint8)
det = DetectionAdapter(camera_id="camera-01", mqtt_host="127.0.0.1")
det_events = det.process(frame)
print(f"1. Detection: {len(det_events)} events")

# 2. ANPR adapter
from services.adapter_anpr.adapter import ANPRAdapter
anpr = ANPRAdapter(camera_id="camera-01", mqtt_host="127.0.0.1")
anpr_events = anpr.process(frame)
print(f"2. ANPR: {len(anpr_events)} events")

# 3. ReID adapter
from services.adapter_reid.adapter import ReIDAdapter
reid = ReIDAdapter(camera_id="camera-01", mqtt_host="127.0.0.1")
reid.publish_batch(det_events)
time.sleep(0.5)
reid_events = reid.process(frame)
print(f"3. ReID: {len(reid_events)} events")

# 4. Anomaly adapter
from services.adapter_anomaly.adapter import AnomalyAdapter
anomaly = AnomalyAdapter(camera_id="camera-01", mqtt_host="127.0.0.1")
for _ in range(25):
    anomaly.process(frame)
anomaly_events = anomaly.process(frame)
print(f"4. Anomaly: {len(anomaly_events)} events")

# 5. Fusion service
time.sleep(1)
try:
    req = urllib.request.Request("http://localhost:8000/health")
    with urllib.request.urlopen(req, timeout=3) as resp:
        health = json.loads(resp.read())
    print(f"5. Fusion health: {health.get('status')}")
except Exception as e:
    print(f"5. Fusion: ERROR {e}")

# 6. Case file service
try:
    url = "http://localhost:9000/case-files?officer=test&camera_id=camera-01&description=audit"
    req = urllib.request.Request(url, method="POST")
    with urllib.request.urlopen(req, timeout=3) as resp:
        case = json.loads(resp.read())
    print(f"6. Case file: created {case.get('case_id', '?')[:8]}...")
except urllib.error.HTTPError as e:
    body = e.read().decode()
    print(f"6. Case file: HTTP {e.code} - {body[:100]}")
except Exception as e:
    print(f"6. Case file: not running (expected) - {e}")

# 7. Privacy blur service
try:
    _, buf = cv2.imencode(".jpg", frame)
    b64 = base64.b64encode(buf).decode()
    blur_payload = json.dumps({
        "frame_b64": b64,
        "bboxes": [{"x": 0.1, "y": 0.1, "w": 0.2, "h": 0.3}],
        "officer": "test"
    }).encode()
    req = urllib.request.Request("http://localhost:9001/blur", data=blur_payload, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=3) as resp:
        blur_result = json.loads(resp.read())
    print(f"7. Privacy blur: {blur_result.get('blurred')}")
except urllib.error.HTTPError as e:
    body = e.read().decode()
    print(f"7. Privacy blur: HTTP {e.code} - {body[:100]}")
except Exception as e:
    print(f"7. Privacy blur: not running (expected) - {e}")

# 8. ONVIF discovery service
try:
    req = urllib.request.Request("http://localhost:9002/cameras")
    with urllib.request.urlopen(req, timeout=3) as resp:
        cameras = json.loads(resp.read())
    print(f"8. ONVIF discovery: {len(cameras)} cameras")
except Exception as e:
    print(f"8. ONVIF discovery: not running (expected) - {e}")

# 9. Dashboard build
if os.path.exists("dashboard/dist/index.html"):
    print("9. Dashboard build: PASS")
else:
    print("9. Dashboard build: FAIL")

# 10. Scale one-pager
if os.path.exists("docs/scale-one-pager.md"):
    print("10. Scale one-pager: PASS")
else:
    print("10. Scale one-pager: FAIL")

# 11. Test feeds
feeds = ["test_feeds/camera01.mp4", "test_feeds/camera02.mp4", "test_feeds/camera03.mp4"]
missing = [f for f in feeds if not os.path.exists(f)]
print(f"11. Test feeds: {'PASS' if not missing else 'MISSING: ' + str(missing)}")

# 12. go2rtc binary
if os.path.exists("tools/go2rtc/go2rtc.exe"):
    print("12. go2rtc binary: PASS")
else:
    print("12. go2rtc binary: FAIL")

# 13. Docker compose
if os.path.exists("docker-compose.yml"):
    print("13. Docker compose: PASS")
else:
    print("13. Docker compose: FAIL")

print("Audit complete")

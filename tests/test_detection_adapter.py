import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import cv2
import urllib.request
import numpy as np
from services.adapter_detection.adapter import DetectionAdapter

# Download a real test image with people
url = "https://ultralytics.com/images/bus.jpg"
urllib.request.urlretrieve(url, "test_bus.jpg")
frame = cv2.imread("test_bus.jpg")
print("Test image shape:", frame.shape)

adapter = DetectionAdapter(camera_id="test-cam")
events = adapter.process(frame)
print(f"Detections: {len(events)}")
for e in events[:5]:
    print(f"  {e.event_type}: {e.entity_type} conf={e.confidence:.2f} bbox={e.bbox}")

# Cleanup
os.remove("test_bus.jpg")
print("Phase 3 detection adapter: PASS" if len(events) > 0 else "Phase 3 detection adapter: FAIL")

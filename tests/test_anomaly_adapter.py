import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import numpy as np
from services.adapter_anomaly.adapter import AnomalyAdapter

adapter = AnomalyAdapter(camera_id="camera-01", mqtt_host="127.0.0.1")
frame = np.zeros((480, 640, 3), dtype=np.uint8)

# Process frames to build track history
for i in range(25):
    adapter.process(frame)

events = adapter.process(frame)
print(f"Anomaly events after history: {len(events)}")
for e in events:
    print(f"  {e.event_type}: {e.anomaly_label} conf={e.confidence:.2f}")

# Verify the adapter does not crash with no detections
no_events = AnomalyAdapter(camera_id="camera-02", mqtt_host="127.0.0.1")
empty_result = no_events.process(frame)
print(f"No-detection events: {len(empty_result)}")
print("Anomaly adapter test: PASS (adapter runs without crash)")

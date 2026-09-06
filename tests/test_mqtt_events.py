import json
import time
import paho.mqtt.client as mqtt

client = mqtt.Client()
client.connect("localhost", 1883, 60)
client.loop_start()

event = {
    "event_id": "test-001",
    "camera_id": "camera-01",
    "timestamp": "2026-09-03T21:47:00Z",
    "event_type": "detection",
    "entity_type": "person",
    "bbox": {"x": 0.1, "y": 0.2, "w": 0.15, "h": 0.3},
    "confidence": 0.85,
    "track_id": "track_001",
    "source_repo": "test",
    "requires_authorization": False
}

for i in range(5):
    event["event_id"] = f"test-{i:03d}"
    event["timestamp"] = f"2026-09-03T21:47:{i:02d}Z"
    client.publish("fuse/events/all", json.dumps(event))
    print(f"Published event {i}")

time.sleep(1)
client.loop_stop()
client.disconnect()
print("Done")

import urllib.request
import json
import time

time.sleep(5)

r = urllib.request.urlopen("http://127.0.0.1:8000/health")
health = json.loads(r.read())
print("Health:", health)

r = urllib.request.urlopen("http://127.0.0.1:8000/events?limit=20")
data = json.loads(r.read())
events = data.get("events", []) if isinstance(data, dict) else data
print(f"Total events received: {len(events)}")

event_types = {}
for e in events:
    et = e.get("event_type", "unknown")
    event_types[et] = event_types.get(et, 0) + 1

print("Event type breakdown:", event_types)

required_fields = [
    "event_id", "camera_id", "timestamp", "event_type", "entity_type",
    "bbox", "confidence", "track_id", "source_repo", "requires_authorization"
]
all_valid = True
for e in events:
    for field in required_fields:
        if field not in e:
            print(f"MISSING FIELD: {field}")
            all_valid = False

if all_valid and len(events) > 0:
    print("PHASE 1 TEST: PASSED")
else:
    print("PHASE 1 TEST: FAILED")

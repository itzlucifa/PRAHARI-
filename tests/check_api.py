import urllib.request
import json

try:
    r = urllib.request.urlopen("http://127.0.0.1:8000/health", timeout=5)
    print("Health:", r.read().decode())
except Exception as e:
    print("Health check failed:", e)

try:
    r = urllib.request.urlopen("http://127.0.0.1:8000/events", timeout=5)
    data = json.loads(r.read())
    events = data.get("events", [])
    print(f"Events count: {len(events)}")
    if events:
        print("Latest event:", json.dumps(events[0], indent=2)[:400])
except Exception as e:
    print("Events check failed:", e)

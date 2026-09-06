"""
PRAHARI Demo Launcher
Launches the demo stack and injects demo events.
"""
import os
import sys
import time
import json
import uuid
import random
import threading
import subprocess
from datetime import datetime, timezone

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Configuration
FUSION_URL = os.getenv("FUSION_URL", "http://localhost:8000")
DASHBOARD_URL = "http://localhost:5173"
EVENTS_ENDPOINT = f"{FUSION_URL}/events"
CAMERAS = ["camera-01", "camera-02", "camera-03"]
EVENT_TYPES = ["detection", "anpr_read", "reid_match", "anomaly", "face_match"]

# Demo event templates
DEMO_EVENTS = {
    "detection": {
        "event_type": "detection",
        "entity_type": "person",
        "confidence": 0.92,
        "track_id": "track_{n}",
        "source_repo": "ultralytics",
        "requires_authorization": False,
    },
    "anpr_read": {
        "event_type": "anpr_read",
        "entity_type": "vehicle",
        "confidence": 0.88,
        "track_id": "track_{n}",
        "plate_text": "GJ{region}{letters}{numbers}",
        "source_repo": "indian-anpr",
        "requires_authorization": False,
    },
    "reid_match": {
        "event_type": "reid_match",
        "entity_type": "person",
        "confidence": 0.85,
        "track_id": "track_{n}",
        "embedding_id": "embed_{hash}",
        "source_repo": "torchreid",
        "requires_authorization": False,
    },
    "anomaly": {
        "event_type": "anomaly",
        "entity_type": "person",
        "confidence": 0.78,
        "track_id": "track_{n}",
        "anomaly_label": "loitering",
        "source_repo": "anomaly-rules",
        "requires_authorization": False,
    },
    "face_match": {
        "event_type": "face_match",
        "entity_type": "person",
        "confidence": 0.91,
        "track_id": "track_{n}",
        "embedding_id": "face_embed_{hash}",
        "source_repo": "insightface",
        "requires_authorization": True,
    },
}


def generate_plate():
    regions = ["01", "02", "03", "04", "05", "06", "07", "08", "09", "10"]
    letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    numbers = "0123456789"
    region = random.choice(regions)
    l1 = random.choice(letters)
    l2 = random.choice(letters)
    n1 = random.choice(numbers)
    n2 = random.choice(numbers)
    l3 = random.choice(letters)
    l4 = random.choice(letters)
    n3 = random.choice(numbers)
    n4 = random.choice(numbers)
    n5 = random.choice(numbers)
    n6 = random.choice(numbers)
    return f"GJ{region}{l1}{l2}{n1}{n2}{l3}{l4}{n3}{n4}{n5}{n6}"


def generate_demo_event(event_type, camera_id, event_counter):
    template = DEMO_EVENTS.get(event_type, DEMO_EVENTS["detection"]).copy()
    template["event_id"] = f"demo-{event_counter:06d}"
    template["camera_id"] = camera_id
    template["timestamp"] = datetime.now(timezone.utc).isoformat()
    template["bbox"] = {
        "x": round(random.uniform(0.1, 0.8), 3),
        "y": round(random.uniform(0.1, 0.8), 3),
        "w": round(random.uniform(0.05, 0.2), 3),
        "h": round(random.uniform(0.1, 0.4), 3),
    }

    for key, value in template.items():
        if isinstance(value, str) and "{n}" in value:
            template[key] = value.replace("{n}", str(event_counter))
        if isinstance(value, str) and "{hash}" in value:
            template[key] = value.replace("{hash}", uuid.uuid4().hex[:12])
        if isinstance(value, str) and "{region}" in value:
            template[key] = value.replace("{region}", random.choice(["01", "02", "03", "04", "05"]))
        if isinstance(value, str) and "{letters}" in value:
            template[key] = value.replace("{letters}", random.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ") + random.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ"))
        if isinstance(value, str) and "{numbers}" in value:
            template[key] = value.replace("{numbers}", str(random.randint(1000, 9999)))

    if template.get("plate_text") and "{region}" in template["plate_text"]:
        template["plate_text"] = generate_plate()

    return template


def inject_demo_events(count=50, interval=0.5):
    import urllib.request
    import urllib.error

    print(f"Injecting {count} demo events...")
    event_counter = 0

    for i in range(count):
        event_type = random.choice(EVENT_TYPES)
        camera_id = random.choice(CAMERAS)
        event = generate_demo_event(event_type, camera_id, event_counter)
        event_counter += 1

        try:
            data = json.dumps(event).encode("utf-8")
            req = urllib.request.Request(
                EVENTS_ENDPOINT,
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                if resp.status == 200:
                    if i % 10 == 0:
                        print(f"Injected {i+1}/{count} events...")
        except Exception as e:
            print(f"Error injecting event: {e}")

        time.sleep(interval)

    print(f"Injected {count} events successfully")


def start_demo_events_stream(duration=300, events_per_second=2):
    print(f"Starting live event stream for {duration} seconds...")

    interval = 1.0 / events_per_second
    end_time = time.time() + duration

    while time.time() < end_time:
        inject_demo_events(count=1, interval=0)
        time.sleep(interval)

    print("Live event stream stopped")


def verify_services():
    import urllib.request

    print("Verifying services...")

    try:
        req = urllib.request.Request(f"{FUSION_URL}/health")
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
            print(f"Fusion service: {data}")
    except Exception as e:
        print(f"Fusion service not running: {e}")
        return False

    try:
        req = urllib.request.Request(DASHBOARD_URL)
        with urllib.request.urlopen(req, timeout=5) as resp:
            print(f"Dashboard: status {resp.status}")
    except Exception as e:
        print(f"Dashboard not running: {e}")
        return False

    return True


def print_demo_instructions():
    print(f"Dashboard: {DASHBOARD_URL}")
    print(f"Fusion API: {FUSION_URL}")


if __name__ == "__main__":
    print("PRAHARI Demo Launcher")

    if not verify_services():
        print("\nERROR: Required services not running!")
        print("Please start:")
        print("  1. Fusion service: cd services/fusion-service && python -m uvicorn app:app --host 0.0.0.0 --port 8000")
        print("  2. Dashboard: cd dashboard && npm run dev")
        sys.exit(1)

    print("All services verified")

    print_demo_instructions()

    print("Options:")
    print("  1. Inject 50 demo events (historical data)")
    print("  2. Start live event stream (5 min)")
    print("  3. Both (1 then 2)")
    print("  4. Just show instructions")

    choice = input("\nEnter choice (1-4): ").strip()

    if choice == "1":
        inject_demo_events(count=50, interval=0.1)
    elif choice == "2":
        start_demo_events_stream(duration=300, events_per_second=2)
    elif choice == "3":
        inject_demo_events(count=50, interval=0.1)
        time.sleep(2)
        start_demo_events_stream(duration=300, events_per_second=2)
    elif choice == "4":
        pass
    else:
        print("Invalid choice, exiting...")

    print("Demo launcher complete")
    print(f"Dashboard: {DASHBOARD_URL}")
    print(f"Fusion API: {FUSION_URL}")

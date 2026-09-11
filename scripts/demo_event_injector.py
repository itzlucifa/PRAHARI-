"""
PRAHARI Demo Event Injector
============================
Injects realistic demo events into the running fusion service.
No production code is modified.
"""
import os
import sys
import json
import time
import uuid
import random
import urllib.request
import urllib.error
from datetime import datetime, timezone

FUSION_URL = "http://localhost:8000/events"
CAMERAS = ["camera-01", "camera-02", "camera-03"]
EVENT_TYPES = ["detection", "anpr_read", "reid_match", "anomaly", "face_match"]

PLATES = [
    "GJ01AB1234", "GJ02CD5678", "GJ03EF9012", "GJ04GH3456", "GJ05IJ7890",
    "GJ06KL2345", "GJ07MN6789", "GJ08OP0123", "GJ09QR4567", "GJ10ST8901",
]

TRACKS = [f"track_{i:03d}" for i in range(1, 51)]
EMBEDDINGS = [f"embed_{uuid.uuid4().hex[:12]}" for _ in range(20)]
ANOMALIES = ["loitering", "crowd_forming", "abandoned_object", "running", "unusual_movement", "gunshot", "glass_break", "scream"]

counter = [0]


def generate_event(event_type=None, camera_id=None):
    """Generate a realistic demo event."""
    counter[0] += 1
    event_id = f"demo-{counter[0]:06d}"

    if event_type is None:
        event_type = random.choices(
            EVENT_TYPES,
            weights=[50, 20, 15, 10, 5],
            k=1
        )[0]

    if camera_id is None:
        camera_id = random.choice(CAMERAS)

    event = {
        "event_id": event_id,
        "camera_id": camera_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event_type": event_type,
        "entity_type": "person" if event_type in ["detection", "reid_match", "face_match", "anomaly"] else "vehicle",
        "bbox": {
            "x": round(random.uniform(0.05, 0.85), 3),
            "y": round(random.uniform(0.05, 0.85), 3),
            "w": round(random.uniform(0.05, 0.25), 3),
            "h": round(random.uniform(0.1, 0.5), 3),
        },
        "confidence": round(random.uniform(0.7, 0.98), 2),
        "track_id": random.choice(TRACKS),
        "source_repo": {
            "detection": "ultralytics",
            "anpr_read": "indian-anpr",
            "reid_match": "torchreid",
            "anomaly": "anomaly-rules",
            "face_match": "insightface",
        }.get(event_type, "unknown"),
        "requires_authorization": event_type == "face_match",
    }

    if event_type == "anpr_read":
        event["plate_text"] = random.choice(PLATES)
    elif event_type in ["reid_match", "face_match"]:
        event["embedding_id"] = random.choice(EMBEDDINGS)
    elif event_type == "anomaly":
        event["anomaly_label"] = random.choice(ANOMALIES)

    return event


def inject_event(event):
    """Inject a single event via HTTP POST."""
    try:
        data = json.dumps(event).encode("utf-8")
        req = urllib.request.Request(
            FUSION_URL,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status == 200
    except Exception as e:
        print(f"[INJECTOR] Error: {e}")
        return False


def inject_batch(count=10, delay=0.1):
    """Inject a batch of events."""
    success = 0
    for _ in range(count):
        event = generate_event()
        if inject_event(event):
            success += 1
        time.sleep(delay)
    return success


def inject_historical(total=100, period_seconds=60):
    """Inject historical events simulating past activity."""
    print(f"[INJECTOR] Injecting {total} historical events over {period_seconds}s...")
    interval = period_seconds / total
    success = 0

    for i in range(total):
        event = generate_event()
        # Backdate timestamps
        event["timestamp"] = (
            datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        )
        if inject_event(event):
            success += 1
        if i % 20 == 0:
            print(f"[INJECTOR] Progress: {i+1}/{total}")
        time.sleep(interval)

    print(f"[INJECTOR] Historical injection complete: {success}/{total} events")
    return success


def start_live_stream(events_per_second=2, duration=None):
    """Start a live event stream."""
    print(f"[INJECTOR] Starting live stream: {events_per_second} eps")
    if duration:
        print(f"[INJECTOR] Will run for {duration} seconds")

    interval = 1.0 / events_per_second
    start_time = time.time()
    count = 0

    try:
        while True:
            event = generate_event()
            if inject_event(event):
                count += 1
                if count % 10 == 0:
                    print(f"[INJECTOR] Live: {count} events injected")
            time.sleep(interval)

            if duration and (time.time() - start_time) >= duration:
                break
    except KeyboardInterrupt:
        pass

    print(f"[INJECTOR] Live stream stopped. Total: {count} events")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="PRAHARI Demo Event Injector")
    parser.add_argument("--batch", type=int, default=10, help="Inject N events quickly")
    parser.add_argument("--historical", type=int, default=100, help="Inject N historical events")
    parser.add_argument("--live", action="store_true", help="Start live event stream")
    parser.add_argument("--eps", type=float, default=2.0, help="Events per second for live stream")
    parser.add_argument("--duration", type=int, default=None, help="Live stream duration in seconds")
    parser.add_argument("--url", default=FUSION_URL, help="Fusion service URL")

    args = parser.parse_args()

    FUSION_URL = args.url

    if args.batch:
        inject_batch(args.batch)

    if args.historical:
        inject_historical(args.historical)

    if args.live:
        start_live_stream(args.eps, args.duration)

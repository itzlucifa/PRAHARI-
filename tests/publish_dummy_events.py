"""Dummy event publisher — continuously publishes test DetectionEvents to MQTT."""
import sys
import os
import time
import random

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.chdir(os.path.join(os.path.dirname(__file__), ".."))

from shared.events import DetectionEvent
from shared.adapter_base import BaseAdapter
import paho.mqtt.client as mqtt


class DummyPublisher(BaseAdapter):
    def __init__(self):
        super().__init__(
            camera_id=f"camera-{random.randint(1,3)}",
            mqtt_host="127.0.0.1",
            mqtt_port=1883,
            source_repo="dummy"
        )
        self.frame_count = 0
        print(f"Publisher initialized for {self.camera_id}", flush=True)

    def process(self, frame=None) -> list[DetectionEvent]:
        self.frame_count += 1
        events = []

        if self.frame_count % 5 == 0:
            events.append(self._build_event(
                "detection", "person",
                {"x": random.uniform(0.1, 0.7), "y": random.uniform(0.1, 0.5), "w": 0.15, "h": 0.3},
                random.uniform(0.7, 0.95),
                track_id=f"p_{random.randint(1, 20)}",
            ))

        if self.frame_count % 10 == 0:
            plates = ["MH12AB1234", "GJ05CD5678", "MH04XY9999"]
            events.append(self._build_event(
                "anpr_read", "vehicle",
                {"x": random.uniform(0.2, 0.6), "y": random.uniform(0.3, 0.7), "w": 0.25, "h": 0.15},
                random.uniform(0.8, 0.98),
                track_id=f"v_{random.randint(1, 20)}",
                plate_text=random.choice(plates),
            ))

        if self.frame_count % 30 == 0:
            anomalies = ["loitering", "running", "crowd_forming"]
            events.append(self._build_event(
                "anomaly", "person",
                {"x": 0.3, "y": 0.3, "w": 0.2, "h": 0.4},
                0.82,
                anomaly_label=random.choice(anomalies),
            ))

        return events


if __name__ == "__main__":
    publisher = DummyPublisher()
    print("Dummy publisher started. Publishing events to MQTT...", flush=True)
    while True:
        events = publisher.process()
        for e in events:
            publisher.publish(e)
            print(f"Published: {e.event_type} on {publisher.camera_id}", flush=True)
        time.sleep(2)

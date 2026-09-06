"""
Test script: verifies the canonical event schema and adapter base class.
Run: python tests/test_spine.py
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import json
from shared.events import DetectionEvent, TOPIC_EVENTS, TOPIC_DETECTIONS
from shared.adapter_base import DummyAdapter


def test_event_schema():
    """Test that DetectionEvent serializes/deserializes correctly."""
    event = DetectionEvent(
        camera_id="camera-01",
        event_type="detection",
        entity_type="person",
        bbox={"x": 0.1, "y": 0.2, "w": 0.15, "h": 0.3},
        confidence=0.85,
        track_id="track_001",
        source_repo="test",
    )
    json_str = event.to_json()
    data = json.loads(json_str)

    assert data["camera_id"] == "camera-01"
    assert data["event_type"] == "detection"
    assert data["entity_type"] == "person"
    assert data["bbox"] == {"x": 0.1, "y": 0.2, "w": 0.15, "h": 0.3}
    assert data["confidence"] == 0.85
    assert data["track_id"] == "track_001"
    assert data["source_repo"] == "test"
    assert "event_id" in data
    assert "timestamp" in data
    print("Event schema serialization test passed")


def test_deserialization():
    """Test that DetectionEvent can be reconstructed from dict."""
    event = DetectionEvent(
        camera_id="camera-02",
        event_type="anpr_read",
        entity_type="vehicle",
        bbox={"x": 0.5, "y": 0.5, "w": 0.2, "h": 0.1},
        confidence=0.92,
        plate_text="MH12AB1234",
    )
    data = json.loads(event.to_json())
    restored = DetectionEvent.from_dict(data)
    assert restored.camera_id == "camera-02"
    assert restored.plate_text == "MH12AB1234"
    assert restored.event_type == "anpr_read"
    print("Event deserialization test passed")


def test_topic_constants():
    """Test that topic constants are defined."""
    assert TOPIC_EVENTS == "fuse/events/all"
    assert "cameras" in TOPIC_DETECTIONS
    assert "+" in TOPIC_DETECTIONS
    print("Topic constants test passed")


def test_dummy_adapter():
    """Test that DummyAdapter produces valid events."""
    adapter = DummyAdapter(camera_id="test-camera", mqtt_host="localhost")
    events = adapter.process(frame=None)
    assert len(events) == 1
    assert events[0].event_type == "detection"
    assert events[0].entity_type == "person"
    assert events[0].source_repo == "dummy"
    assert events[0].confidence == 0.85
    json_str = events[0].to_json()
    data = json.loads(json_str)
    assert data is not None
    print("DummyAdapter test passed")


if __name__ == "__main__":
    test_event_schema()
    test_deserialization()
    test_topic_constants()
    test_dummy_adapter()
    print("All spine tests passed")

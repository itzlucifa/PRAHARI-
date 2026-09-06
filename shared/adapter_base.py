"""
Base adapter class. All adapters inherit from this.
Wraps a repo's native output and publishes canonical DetectionEvents to MQTT.
"""
from __future__ import annotations
import os
import json
import logging
import time
import paho.mqtt.client as mqtt
import requests
from abc import ABC, abstractmethod
from typing import Optional
from shared.events import DetectionEvent, TOPIC_EVENTS

logger = logging.getLogger(__name__)


class BaseAdapter(ABC):
    """
    All adapters:
    1. Consume a normalized stream (from go2rtc or a file source)
    2. Run their wrapped repo's logic
    3. Translate output into DetectionEvent
    4. Publish to MQTT or HTTP fallback
    """

    def __init__(
        self,
        camera_id: str,
        mqtt_host: str = "localhost",
        mqtt_port: int = 1883,
        source_repo: str = "",
        fusion_http_url: Optional[str] = None,
    ):
        self.camera_id = camera_id
        self.mqtt_host = mqtt_host
        self.mqtt_port = mqtt_port
        self.source_repo = source_repo
        self.fusion_http_url = fusion_http_url or os.getenv("FUSION_HTTP_URL", "http://localhost:8000/events")
        self._mqtt: Optional[mqtt.Client] = None
        self._use_http_fallback = False
        self._connect_mqtt()

    def _connect_mqtt(self):
        for attempt in range(3):
            try:
                self._mqtt = mqtt.Client(client_id=f"{self.source_repo}_{self.camera_id}")
                self._mqtt.connect(self.mqtt_host, self.mqtt_port, keepalive=60)
                self._mqtt.loop_start()
                logger.info(f"Connected to MQTT at {self.mqtt_host}:{self.mqtt_port}")
                return
            except Exception as e:
                logger.warning(f"MQTT connect attempt {attempt+1} failed: {e}")
                time.sleep(1)
        logger.warning("MQTT unavailable, using HTTP fallback")
        self._use_http_fallback = True

    @abstractmethod
    def process(self, frame) -> list[DetectionEvent]:
        """Process one frame, return list of DetectionEvents."""
        pass

    def _build_event(
        self,
        event_type: str,
        entity_type: str,
        bbox: dict,
        confidence: float,
        track_id: str = "",
        **kwargs,
    ) -> DetectionEvent:
        """Build a canonical DetectionEvent from repo-native output."""
        return DetectionEvent(
            camera_id=self.camera_id,
            event_type=event_type,
            entity_type=entity_type,
            bbox=bbox,
            confidence=confidence,
            track_id=track_id,
            source_repo=self.source_repo,
            **kwargs,
        )

    def publish(self, event: DetectionEvent):
        """Publish a single event to MQTT or HTTP fallback."""
        if self._use_http_fallback:
            try:
                resp = requests.post(
                    self.fusion_http_url,
                    json=event.to_dict(),
                    timeout=2,
                )
                logger.info(f"HTTP publish: {resp.status_code} for {event.event_type}")
            except Exception as e:
                logger.warning(f"HTTP publish failed: {e}")
        elif self._mqtt:
            topic = TOPIC_EVENTS
            self._mqtt.publish(topic, event.to_json())
            logger.debug(f"Published {event.event_type} for camera {event.camera_id}")

    def publish_batch(self, events: list[DetectionEvent]):
        """Publish multiple events."""
        for e in events:
            self.publish(e)


class DummyAdapter(BaseAdapter):
    """Trivial adapter for proving the spine works end-to-end."""

    def __init__(self, **kwargs):
        super().__init__(source_repo="dummy", **kwargs)

    def process(self, frame) -> list[DetectionEvent]:
        return [
            self._build_event(
                event_type="detection",
                entity_type="person",
                bbox={"x": 0.1, "y": 0.2, "w": 0.15, "h": 0.3},
                confidence=0.85,
                track_id="track_001",
            )
        ]

"""
Simple in-memory event bus for local testing.
Replaces MQTT when running locally without a broker.
"""
import asyncio
import logging
import threading
from collections import defaultdict

logger = logging.getLogger("event-bus")

class EventBus:
    def __init__(self):
        self._subscribers = defaultdict(list)
        self._lock = threading.Lock()
        self._queue = asyncio.Queue()

    def subscribe(self, topic: str, callback):
        with self._lock:
            self._subscribers[topic].append(callback)
        logger.info("Subscribed to topic: %s", topic)

    def publish(self, topic: str, message: str):
        with self._lock:
            callbacks = list(self._subscribers.get(topic, []))
        for callback in callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    asyncio.create_task(callback(message))
                else:
                    callback(message)
            except Exception as exc:
                logger.debug("Callback error: %s", exc)

    def get_queue(self):
        return self._queue


# Global event bus instance
event_bus = EventBus()

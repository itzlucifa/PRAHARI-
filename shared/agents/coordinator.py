"""
PRAHARI Agent Orchestration Layer
==================================
A simplified multi-agent system inspired by Sentigon's 12-agent fleet
and Vision Labs' orchestrator pattern.

The ThreatCoordinator orchestrates five agent roles:
1. Watcher — monitors incoming events for threats
2. Detector — verifies threats using the adversarial verifier
3. Notifier — decides when/what to alert based on rules
4. Investigator — searches for related events across cameras
5. Copilot — handles contextual chat queries

Communication: Redis pub/sub or in-memory event queue
"""
import os
import json
import time
import uuid
import logging
import threading
from datetime import datetime, timezone
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict, deque

logger = logging.getLogger("prahari.agents")


class Severity(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class IncidentStatus(Enum):
    OPEN = "open"
    ACKNOWLEDGED = "acknowledged"
    INVESTIGATING = "investigating"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"


@dataclass
class SurveillanceEvent:
    event_id: str
    camera_id: str
    timestamp: str
    event_type: str
    entity_type: str
    confidence: float
    track_id: str = ""
    bbox: dict = field(default_factory=dict)
    plate_text: str = None
    anomaly_label: str = None
    embedding_id: str = None
    requires_authorization: bool = False
    _received_at: float = field(default_factory=time.time)


@dataclass
class Alert:
    alert_id: str
    event_id: str
    camera_id: str
    severity: Severity
    title: str
    description: str
    confidence: float
    status: str = "open"
    created_at: str = ""
    acknowledged_by: str = None
    incident_id: str = None


class WatcherAgent:
    """Monitors incoming events and identifies potential threats."""

    def __init__(self, coordinator):
        self.coordinator = coordinator
        self.event_history: dict[str, deque] = defaultdict(lambda: deque(maxlen=100))
        self.pattern_cache: dict[str, dict] = {}

    def process_event(self, event: SurveillanceEvent) -> bool:
        """Process an incoming event and decide if it warrants further investigation."""
        self.event_history[event.camera_id].append(event)

        self._detect_patterns(event)

        confidence = event.confidence or 0.0
        if confidence < 0.5:
            return False

        threat_indicators = [
            (event.event_type == "face_match" and event.requires_authorization),
            (event.event_type == "anomaly"),
            (event.event_type == "anpr_read" and self._check_watchlist(event.plate_text)),
            (event.event_type == "reid_match"),
            (confidence >= 0.9),
        ]

        return any(threat_indicators)

    def _check_watchlist(self, plate_text: str) -> bool:
        if not plate_text:
            return False
        watchlist = self.coordinator.config.get("watchlist", {}).get("plates", [])
        return plate_text in watchlist

    def _detect_patterns(self, event: SurveillanceEvent):
        """Detect suspicious patterns across events."""
        camera_events = self.event_history[event.camera_id]
        if len(camera_events) < 3:
            return

        event_types = defaultdict(int)
        for e in camera_events:
            event_types[e.event_type] += 1

        if event_types.get("anomaly", 0) >= 3:
            logger.info("Pattern detected: repeated anomalies on %s", event.camera_id)
            self.coordinator.notify_pattern(
                event.camera_id, "repeated_anomalies",
                f"3+ anomalies in recent history", Severity.MEDIUM
            )


class DetectorAgent:
    """Verifies threats using the adversarial verification model."""

    def __init__(self, coordinator):
        self.coordinator = coordinator
        self.verification_cache: dict[str, dict] = {}

    def verify(self, event: SurveillanceEvent) -> tuple[bool, str]:
        """Verify if a threat is real. Returns (verified, reason)."""
        confidence = event.confidence or 0.0

        thresholds = {
            "detection": 0.6,
            "anpr_read": 0.7,
            "reid_match": 0.75,
            "face_match": 0.8,
            "anomaly": 0.5,
        }
        threshold = thresholds.get(event.event_type, 0.5)

        verified = confidence >= threshold

        if event.event_type == "face_match" and event.requires_authorization:
            if not verified:
                return False, "Unauthorized face not confident enough"
            return True, "Unauthorized access attempt"

        if event.event_type == "anpr_read":
            if self.coordinator.watcher._check_watchlist(event.plate_text):
                return True, f"Watchlist vehicle detected: {event.plate_text}"

        if event.event_type == "reid_match":
            return True, "Person of interest detected across cameras"

        if event.confidence >= 0.95 and event.event_type == "detection" and event.entity_type == "person":
            return True, f"High-confidence person detection ({confidence * 100:.1f}%)"

        reason = f"Confidence {confidence:.2f} vs threshold {threshold} for {event.event_type}"
        return verified, reason


class NotifierAgent:
    """Decides when to send alerts and what channels to use."""

    def __init__(self, coordinator):
        self.coordinator = coordinator
        self.alert_history: dict[str, list] = defaultdict(list)
        self.suppression_rules = {
            "same_camera_cooldown": 60,
            "same_event_cooldown": 30,
            "max_per_minute": 10,
        }

    def evaluate(self, event: SurveillanceEvent, verification_result: tuple[bool, str]) -> Alert:
        """Evaluate if an alert should be fired."""
        verified, reason = verification_result
        if not verified:
            return None

        camera_id = event.camera_id
        now = time.time()

        recent_alerts = [
            a for a in self.alert_history[camera_id]
            if now - a.created_ts < self.suppression_rules["same_camera_cooldown"]
        ]
        if len(recent_alerts) >= self.suppression_rules["max_per_minute"]:
            logger.warning("Alert suppression: too many alerts for %s", camera_id)
            return None

        severity = self._calculate_severity(event, verification_result)

        alert = Alert(
            alert_id=str(uuid.uuid4()),
            event_id=event.event_id,
            camera_id=camera_id,
            severity=severity,
            title=self._generate_title(event, severity),
            description=reason,
            confidence=event.confidence or 0.0,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        alert.created_ts = now

        self.alert_history[camera_id].append(alert)
        self.alert_history[camera_id] = [
            a for a in self.alert_history[camera_id]
            if now - a.created_ts < 300
        ]

        channels = self._select_channels(severity)
        alert.channels = channels
        return alert

    def _calculate_severity(self, event: SurveillanceEvent, verification_result) -> Severity:
        confidence = event.confidence or 0.0

        if event.event_type == "face_match" and event.requires_authorization:
            return Severity.CRITICAL
        if event.event_type == "anomaly":
            return Severity.HIGH
        if event.event_type == "anpr_read":
            return Severity.HIGH if confidence >= 0.8 else Severity.MEDIUM
        if confidence >= 0.9:
            return Severity.HIGH
        if confidence >= 0.75:
            return Severity.MEDIUM
        return Severity.LOW

    def _generate_title(self, event: SurveillanceEvent, severity: Severity) -> str:
        sev_text = severity.value.upper()
        if event.event_type == "face_match":
            return f"{sev_text}: Unauthorized Face Detected"
        if event.event_type == "anpr_read":
            return f"{sev_text}: Vehicle {event.plate_text or 'unknown'} at {event.camera_id}"
        if event.event_type == "anomaly":
            return f"{sev_text}: Anomaly - {event.anomaly_label or 'unknown'} at {event.camera_id}"
        if event.event_type == "reid_match":
            return f"{sev_text}: Person of Interest at {event.camera_id}"
        return f"{sev_text}: Detection at {event.camera_id} (conf: {event.confidence:.2f})"

    def _select_channels(self, severity: Severity) -> list[str]:
        if severity == Severity.CRITICAL:
            return ["websocket", "email", "sms", "webhook"]
        if severity == Severity.HIGH:
            return ["websocket", "email", "webhook"]
        if severity == Severity.MEDIUM:
            return ["websocket", "webhook"]
        return ["websocket"]


class InvestigatorAgent:
    """Searches for related events across cameras."""

    def __init__(self, coordinator):
        self.coordinator = coordinator

    def investigate(self, alert: Alert, event: SurveillanceEvent) -> dict:
        """Find related events across cameras."""
        related_events = []

        for camera_id, history in self.coordinator.watcher.event_history.items():
            if camera_id == event.camera_id:
                continue
            for e in history:
                if self._is_related(e, event):
                    related_events.append({
                        "camera_id": e.camera_id,
                        "event_type": e.event_type,
                        "timestamp": e.timestamp,
                        "confidence": e.confidence,
                    })

        return {
            "incident_id": alert.incident_id,
            "related_events_count": len(related_events),
            "related_events": related_events[:10],
            "timeline": self._build_timeline(event, related_events),
        }

    def _is_related(self, event_a: SurveillanceEvent, event_b: SurveillanceEvent) -> bool:
        time_diff = abs(
            datetime.fromisoformat(event_a.timestamp.replace("Z", "+00:00")).timestamp()
            - datetime.fromisoformat(event_b.timestamp.replace("Z", "+00:00")).timestamp()
        )
        if time_diff > 300:
            return False

        if event_a.track_id and event_b.track_id and event_a.track_id == event_b.track_id:
            return True
        if event_a.event_type == event_b.event_type == "reid_match":
            return True
        if event_a.plate_text and event_b.plate_text and event_a.plate_text == event_b.plate_text:
            return True
        return False

    def _build_timeline(self, event: SurveillanceEvent, related: list) -> list:
        timeline = [{"camera_id": event.camera_id, "event_type": event.event_type, "timestamp": event.timestamp}]
        for e in related:
            timeline.append(e)
        timeline.sort(key=lambda x: x.get("timestamp", ""))
        return timeline


class CopilotAgent:
    """Handles contextual chat queries with full system awareness.

    Inspired by Vision Labs' 19-tool AI assistant — provides tool-like
    capabilities for querying events, incidents, trajectories, and generating
    scene descriptions.
    """

    def __init__(self, coordinator):
        self.coordinator = coordinator
        self.conversation_history: list[dict] = []
        self.max_history = 10

    TOOLS = [
        "query_cameras", "query_alerts", "query_incidents",
        "query_events", "query_trajectory", "predict_trajectory",
        "describe_scene", "query_threats",
    ]

    def respond(self, query: str) -> str:
        """Generate a contextual response to a user query using available tools."""
        query_lower = query.lower()
        self.conversation_history.append({"role": "user", "content": query})
        if len(self.conversation_history) > self.max_history:
            self.conversation_history.pop(0)

        if "track" in query_lower and "camera" in query_lower:
            return self._tool_query_trajectory(query_lower)

        if "where" in query_lower or "path" in query_lower or "movement" in query_lower:
            if "track" in query_lower or "track_id" in query_lower:
                return self._tool_query_trajectory(query_lower)
            return "I can track persons and vehicles across cameras using ReID. Specify a track_id, e.g., 'Show me the trajectory for track_001'."

        if "incident" in query_lower:
            return self._tool_query_incidents(query_lower)

        if "alert" in query_lower:
            return self._tool_query_alerts(query_lower)

        if "camera" in query_lower or "cameras" in query_lower:
            return self._tool_query_cameras()

        if "threat" in query_lower or "danger" in query_lower or "risk" in query_lower:
            return self._tool_query_threats()

        if "event" in query_lower or "events" in query_lower:
            return self._tool_query_events()

        if "tool" in query_lower or "capabilit" in query_lower:
            return f"I have {len(self.TOOLS)} tools available: " + ", ".join(self.TOOLS)

        if "describe" in query_lower or "scene" in query_lower:
            return self._tool_describe_scene(query_lower)

        if "what" in query_lower:
            return self._tool_describe_scene(query_lower)

        return "I can help with: camera status, incidents, alerts, threat detection, cross-camera trajectory tracking, and scene descriptions. Try: 'Where was track_016 seen?' or 'Describe the scene at camera-01'."

    def _tool_query_cameras(self) -> str:
        cameras = self.coordinator.get_cameras()
        if not cameras:
            return "No cameras detected. Ensure camera streams are configured."
        lines = [f"There are {len(cameras)} cameras streaming live:"]
        for c in cameras[:10]:
            event_count = c.get("event_count", 0)
            lines.append(f"  - {c['camera_id']}: {event_count} tracked events")
        return "\n".join(lines)

    def _tool_query_alerts(self) -> str:
        alerts = self.coordinator.get_alerts()
        if not alerts:
            return "No active alerts. All clear."

        sev_counts = defaultdict(int)
        for a in alerts:
            sev_counts[a.get("severity", "medium")] += 1

        response = [f"There are {len(alerts)} active alerts:"]
        for sev in ("critical", "high", "medium", "low"):
            if sev_counts[sev]:
                response.append(f"  - {sev.upper()}: {sev_counts[sev]}")
        recent = alerts[:3]
        response.append("Recent alerts:")
        for a in recent:
            response.append(f"  - [{a.get('severity', '').upper()}] {a.get('title', 'Unknown')} at {a.get('camera_id')}")
        return "\n".join(response)

    def _tool_query_incidents(self, query: str) -> str:
        incidents = self.coordinator.get_incidents()
        if not incidents:
            return "No incidents recorded."

        critical = [i for i in incidents if i.get("severity") == "critical"]
        high = [i for i in incidents if i.get("severity") == "high"]

        if critical:
            response = f"There are {len(critical)} CRITICAL incidents requiring immediate attention:"
            for i in critical[:3]:
                response += f"\n  - {i.get('title')} at {i.get('camera_id')} ({i.get('created_at', '')[:19]})"
            return response

        if high:
            response = f"There are {len(high)} HIGH severity incidents:"
            for i in high[:3]:
                response += f"\n  - {i.get('title')} at {i.get('camera_id')} ({i.get('created_at', '')[:19]})"
            return response

        return f"There are {len(incidents)} total incidents, 0 critical."

    def _tool_query_events(self) -> str:
        events = self.coordinator.get_events()
        if not events:
            return "No recent events."
        types = defaultdict(int)
        for e in events:
            types[e.get("event_type", "unknown")] += 1
        response = f"In the last window: {len(events)} events detected."
        response += " Breakdown: " + ", ".join(f"{k}={v}" for k, v in types.items())
        return response

    def _tool_query_threats(self) -> str:
        threats = [
            e for e in self.coordinator.get_events()
            if (e.get("confidence", 0) >= 0.85 or e.get("event_type") in ("anomaly", "face_match"))
        ]
        if not threats:
            return "No high-confidence threats detected. All cameras are secure."
        response = f"Found {len(threats)} high-confidence threats:"
        for t in threats[:3]:
            response += f"\n  - {t.get('event_type')} at {t.get('camera_id')} (conf: {t.get('confidence', 0):.2f})"
        return response

    def _tool_query_trajectory(self, query_lower: str) -> str:
        track_id = None
        for word in query_lower.replace("?", "").split():
            if word.startswith("track"):
                track_id = word
                break

        if track_id:
            trajectory = self.coordinator.get_trajectory(track_id)
            path = trajectory.get("path", [])
            if not path:
                return f"No trajectory found for {track_id}."
            cameras = trajectory.get("cameras", [])
            response = f"Trajectory for {track_id} ({len(cameras)} cameras visited):"
            for entry in path:
                cam = entry["camera_id"]
                ts = entry["timestamp"][:19] if entry.get("timestamp") else "unknown"
                etype = entry.get("event_type", "unknown")
                response += f"\n  {ts} | {cam} | {etype} (conf: {entry.get('confidence', 0):.2f})"
            prediction = self.coordinator.predict_trajectory(track_id)
            next_cam = prediction.get("predicted_next_camera", "unknown")
            confidence = prediction.get("confidence", 0)
            if next_cam != "unknown" and confidence > 0:
                response += f"\n  Predicted next: {next_cam} (confidence: {confidence:.0%})"
            return response

        track_ids = list(self.coordinator._trajectory_store.keys())[:10]
        if track_ids:
            return f"Known tracks: {', '.join(track_ids[:5])}. Use 'trajectory for track_001' to see details."
        return "No trajectory data available. Tracks are created when entities are detected across cameras."

    def _tool_describe_scene(self, query_lower: str) -> str:
        """Generate a VLM-style natural language scene description."""
        events = self.coordinator.get_events()
        if not events:
            return "No recent activity. All cameras are quiet."

        camera_descriptions = defaultdict(list)
        for e in events[:10]:
            cam = e.get("camera_id", "unknown")
            etype = e.get("event_type", "unknown")
            entity = e.get("entity_type", "unknown")
            conf = e.get("confidence", 0)
            if conf > 0.8:
                camera_descriptions[cam].append(f"{entity} ({etype}, conf {conf:.0%})")

        if not camera_descriptions:
            return "All cameras showing normal activity, no high-confidence detections."

        response = "Scene description:\n"
        for cam, descriptions in camera_descriptions.items():
            response += f"  {cam}: " + ", ".join(descriptions) + "\n"
        response += "\nOverall: Active surveillance with multiple detections across cameras."
        return response


class ThreatCoordinator:
    """
    Main orchestrator for the multi-agent threat detection system.
    Coordinates Watcher, Detector, Notifier, and Investigator agents.
    """

    def __init__(self, config_path: str = None):
        self.config = {}
        self.running = False
        self._lock = threading.Lock()
        self._event_queue: deque = deque(maxlen=1000)
        self._trajectory_store: dict[str, list[dict]] = defaultdict(list)
        self._trajectory_lock = threading.Lock()

        if config_path:
            self._load_config(config_path)

        self.watcher = WatcherAgent(self)
        self.detector = DetectorAgent(self)
        self.notifier = NotifierAgent(self)
        self.investigator = InvestigatorAgent(self)
        self.copilot = CopilotAgent(self)

        self._alert_callbacks: list[callable] = []
        self._incident_callbacks: list[callable] = []

    def _load_config(self, config_path: str):
        try:
            with open(config_path) as f:
                self.config = json.load(f)
            logger.info("Loaded config from %s", config_path)
        except Exception as exc:
            logger.warning("Config load failed: %s", exc)
            self.config = {}

    def register_alert_callback(self, callback: callable):
        self._alert_callbacks.append(callback)

    def register_incident_callback(self, callback: callable):
        self._incident_callbacks.append(callback)

    def process_event(self, event_dict: dict) -> Alert:
        """Main entry point: process an event through the agent pipeline."""
        event = SurveillanceEvent(**{
            k: v for k, v in event_dict.items()
            if k in SurveillanceEvent.__dataclass_fields__
        })

        if event.event_type == "detection" and not event.entity_type:
            event.entity_type = "person"

        if not self.watcher.process_event(event):
            return None

        verification_result = self.detector.verify(event)
        if not verification_result[0]:
            return None

        alert = self.notifier.evaluate(event, verification_result)
        if alert is None:
            return None

        investigation = self.investigator.investigate(alert, event)
        alert.investigation = investigation

        for cb in self._alert_callbacks:
            try:
                cb(alert)
            except Exception as exc:
                logger.warning("Alert callback failed: %s", exc)

        self._create_incident(alert, event)

        logger.info(
            "Alert generated: %s | camera=%s | severity=%s | confidence=%.2f",
            alert.title, alert.camera_id, alert.severity.value, alert.confidence
        )

        return alert

    def _create_incident(self, alert: Alert, event: SurveillanceEvent):
        """Create or update an incident from an alert."""
        incident = {
            "id": str(uuid.uuid4()),
            "camera_id": alert.camera_id,
            "severity": alert.severity.value,
            "status": "open",
            "title": alert.title,
            "description": alert.description,
            "event_types": event.event_type,
            "created_at": alert.created_at,
            "updated_at": alert.created_at,
            "acknowledged_by": None,
            "assigned_to": None,
            "resolved_at": None,
            "notes": None,
        }
        alert.incident_id = incident["id"]

        for cb in self._incident_callbacks:
            try:
                cb(incident)
            except Exception as exc:
                logger.warning("Incident callback failed: %s", exc)

    def get_events(self) -> list:
        """Get recent events from the watcher's history."""
        all_events = []
        with self._lock:
            for camera_id, history in self.watcher.event_history.items():
                for e in history:
                    all_events.append({
                        "event_id": e.event_id,
                        "camera_id": e.camera_id,
                        "timestamp": e.timestamp,
                        "event_type": e.event_type,
                        "entity_type": e.entity_type,
                        "confidence": e.confidence,
                    })
        return sorted(all_events, key=lambda x: x.get("_received_at", 0), reverse=True)[:50]

    def get_alerts(self) -> list:
        """Get recent alerts from the notifier's history."""
        alerts = []
        for camera_id, history in self.notifier.alert_history.items():
            for a in history:
                alerts.append({
                    "alert_id": a.alert_id,
                    "camera_id": a.camera_id,
                    "severity": a.severity.value,
                    "title": a.title,
                    "description": a.description,
                    "confidence": a.confidence,
                    "status": a.status,
                    "created_at": a.created_at,
                    "incident_id": a.incident_id,
                    "channels": getattr(a, "channels", ["websocket"]),
                })
        return sorted(alerts, key=lambda x: x.get("created_at", ""), reverse=True)[:50]

    def get_incidents(self) -> list:
        """Get incidents from in-memory store."""
        incidents = []
        for camera_id, history in self.notifier.alert_history.items():
            for a in history:
                if a.incident_id:
                    incidents.append({
                        "id": a.incident_id,
                        "camera_id": a.camera_id,
                        "severity": a.severity.value,
                        "status": "open",
                        "title": a.title,
                        "description": a.description,
                        "created_at": a.created_at,
                    })
        return sorted(incidents, key=lambda x: x.get("created_at", ""), reverse=True)[:50]

    def get_cameras(self) -> list:
        """Get registered cameras."""
        return [
            {"camera_id": cid, "event_count": len(history)}
            for cid, history in self.watcher.event_history.items()
        ]

    def query(self, q: str) -> str:
        """Route a chat query through the Copilot agent."""
        return self.copilot.respond(q)

    def notify_pattern(self, camera_id: str, pattern_type: str, message: str, severity: Severity):
        """Called by Watcher when a pattern is detected."""
        logger.info("Pattern detected: %s on %s (severity: %s)", pattern_type, camera_id, severity.value)

    def add_trajectory_point(self, track_id: str, camera_id: str, event_type: str,
                              entity_type: str, bbox: dict, confidence: float,
                              timestamp: str, embedding_id: str = None, _received_at: float = None):
        """Add a point to the cross-camera trajectory for a tracked entity."""
        if _received_at is None:
            _received_at = time.time()
        with self._trajectory_lock:
            entry = {
                "camera_id": camera_id,
                "timestamp": timestamp,
                "event_type": event_type,
                "entity_type": entity_type,
                "bbox": bbox,
                "confidence": confidence,
                "embedding_id": embedding_id,
                "_received_at": _received_at,
            }
            self._trajectory_store[track_id].append(entry)
            if len(self._trajectory_store[track_id]) > 500:
                self._trajectory_store[track_id] = self._trajectory_store[track_id][-500:]

    def get_trajectory(self, track_id: str) -> dict:
        """Get the trajectory for a tracked entity."""
        with self._trajectory_lock:
            if track_id not in self._trajectory_store:
                return {"track_id": track_id, "path": [], "cameras": []}
            path = self._trajectory_store[track_id]
            cameras = []
            seen = set()
            for entry in path:
                if entry["camera_id"] not in seen:
                    cameras.append(entry["camera_id"])
                    seen.add(entry["camera_id"])
            return {
                "track_id": track_id,
                "cameras": cameras,
                "path": list(path),
                "total_events": len(path),
                "duration_seconds": (path[-1].get("_received_at", 0) - path[0].get("_received_at", 0)) if len(path) > 1 else 0,
            }

    def predict_trajectory(self, track_id: str) -> dict:
        """Predict next camera for a tracked entity."""
        with self._trajectory_lock:
            if track_id not in self._trajectory_store:
                return {"track_id": track_id, "prediction": None}
            path = self._trajectory_store[track_id]
            if len(path) < 2:
                return {"track_id": track_id, "prediction": "Insufficient data"}
            unique_cameras = list(dict.fromkeys([e["camera_id"] for e in path]))
            if len(unique_cameras) < 2:
                return {"track_id": track_id, "prediction": "Single camera only"}
            last_cam = unique_cameras[-1]
            transitions = defaultdict(lambda: defaultdict(int))
            for i in range(len(unique_cameras) - 1):
                transitions[unique_cameras[i]][unique_cameras[i + 1]] += 1
            if last_cam in transitions:
                next_cameras = sorted(transitions[last_cam].items(), key=lambda x: x[1], reverse=True)
                prediction = next_cameras[0][0] if next_cameras else "unknown"
                confidence = next_cameras[0][1] / sum(transitions[last_cam].values()) if next_cameras else 0
            else:
                prediction = "unknown"
                confidence = 0.0
            return {
                "track_id": track_id,
                "last_camera": last_cam,
                "predicted_next_camera": prediction,
                "confidence": round(confidence, 2),
                "camera_sequence": unique_cameras,
                "path_length": len(path),
            }

    def start(self):
        """Start the coordinator thread."""
        self.running = True
        logger.info("ThreatCoordinator started with %d agents", 5)

    def stop(self):
        """Stop the coordinator."""
        self.running = False
        logger.info("ThreatCoordinator stopped")

import os
import sys
import time
import json
import math
import logging
import threading
from collections import deque
from datetime import datetime, timezone

import cv2
import numpy as np
import paho.mqtt.client as mqtt

from shared.adapter_base import BaseAdapter
from shared.events import DetectionEvent, TOPIC_EVENTS

logger = logging.getLogger("anomaly-adapter")


class AnomalyAdapter(BaseAdapter):
    def __init__(self, camera_id: str, **kwargs):
        super().__init__(source_repo="anomaly-rules", camera_id=camera_id, **kwargs)
        self._track_history: dict[str, deque] = {}
        self._track_history_lock = threading.Lock()
        self._frame_count = 0
        self._last_anomaly_time: dict[str, float] = {}
        self._anomaly_cooldown = kwargs.get("anomaly_cooldown", 30.0)
        self._loitering_threshold = kwargs.get("loitering_threshold", 120)
        self._crowd_threshold = kwargs.get("crowd_threshold", 5)
        self._motion_threshold = kwargs.get("motion_threshold", 0.15)
        self._prev_gray = None
        self._motion_history = deque(maxlen=30)
        self._last_person_detections: list[dict] = []

    def update_person_detections(self, detections: list[dict]):
        self._last_person_detections = detections

    def _update_track_history(self, track_id: str, bbox: dict, timestamp: float):
        with self._track_history_lock:
            if track_id not in self._track_history:
                self._track_history[track_id] = deque(maxlen=300)
            self._track_history[track_id].append({"bbox": bbox, "timestamp": timestamp})

    def _detect_loitering(self, track_id: str) -> str | None:
        with self._track_history_lock:
            history = list(self._track_history.get(track_id, []))
        if len(history) < self._loitering_threshold:
            return None
        first = history[0]
        last = history[-1]
        dx = abs(last["bbox"]["x"] - first["bbox"]["x"])
        dy = abs(last["bbox"]["y"] - first["bbox"]["y"])
        duration = last["timestamp"] - first["timestamp"]
        if dx < 0.05 and dy < 0.05 and duration > 10:
            return "loitering"
        return None

    def _detect_crowd(self) -> str | None:
        persons = [d for d in self._last_person_detections if d.get("entity_type") == "person"]
        if len(persons) >= self._crowd_threshold:
            return "crowd_forming"
        return None

    def _detect_unusual_movement(self, frame) -> str | None:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (21, 21), 0)
        if self._prev_gray is None:
            self._prev_gray = gray
            return None
        frame_delta = cv2.absdiff(self._prev_gray, gray)
        thresh = cv2.threshold(frame_delta, 25, 255, cv2.THRESH_BINARY)[1]
        motion_ratio = float(np.sum(thresh)) / float(thresh.shape[0] * thresh.shape[1] * 255)
        self._motion_history.append(motion_ratio)
        self._prev_gray = gray
        if len(self._motion_history) < 10:
            return None
        avg_motion = float(np.mean(list(self._motion_history)))
        if avg_motion > self._motion_threshold:
            return "unusual_movement"
        return None

    def _can_emit_anomaly(self, anomaly_type: str, track_id: str) -> bool:
        key = f"{anomaly_type}:{track_id}" if track_id else anomaly_type
        now = time.time()
        last = self._last_anomaly_time.get(key, 0)
        if now - last < self._anomaly_cooldown:
            return False
        self._last_anomaly_time[key] = now
        return True

    def process(self, frame) -> list[DetectionEvent]:
        self._frame_count += 1
        now = time.time()
        events = []
        for det in self._last_person_detections:
            track_id = det.get("track_id", "")
            if track_id:
                self._update_track_history(track_id, det.get("bbox", {}), now)
                anomaly = self._detect_loitering(track_id)
                if anomaly and self._can_emit_anomaly(anomaly, track_id):
                    events.append(
                        self._build_event(
                            event_type="anomaly",
                            entity_type="person",
                            bbox=det.get("bbox", {}),
                            confidence=0.7,
                            track_id=track_id,
                            anomaly_label=anomaly,
                        )
                    )
        crowd_anomaly = self._detect_crowd()
        if crowd_anomaly and self._can_emit_anomaly(crowd_anomaly, ""):
            events.append(
                self._build_event(
                    event_type="anomaly",
                    entity_type="person",
                    bbox={"x": 0, "y": 0, "w": 0, "h": 0},
                    confidence=0.6,
                    track_id="",
                    anomaly_label=crowd_anomaly,
                )
            )
        movement_anomaly = self._detect_unusual_movement(frame)
        if movement_anomaly and self._can_emit_anomaly(movement_anomaly, ""):
            events.append(
                self._build_event(
                    event_type="anomaly",
                    entity_type="object",
                    bbox={"x": 0, "y": 0, "w": 0, "h": 0},
                    confidence=0.5,
                    track_id="",
                    anomaly_label=movement_anomaly,
                )
            )
        return events


class AudioEventDetector:
    """
    Detects audio events using spectral analysis.
    Inspired by Sentigon's audio event detection and OpenDVR's audio analysis.

    Detects: gunshot, glass_break, scream, loud_bang
    """

    SAMPLE_RATE = 16000
    FRAME_SIZE = 1024
    N_FFT = 1024
    HOP_LENGTH = 512

    GUNSHOT_FREQ_RANGE = (2000, 6000)
    GUNSHOT_DURATION_MS = (10, 100)
    GUNSHOT_DB_THRESHOLD = 20

    GLASS_BREAK_FREQ_RANGE = (4000, 10000)
    GLASS_BREAK_DURATION_MS = (50, 500)
    GLASS_BREAK_DB_THRESHOLD = 15

    SCREAM_FREQ_RANGE = (2000, 5000)
    SCREAM_DURATION_MS = (500, 5000)
    SCREAM_DB_THRESHOLD = 18

    BANG_DB_THRESHOLD = 25
    BANG_FREQ_RANGE = (100, 2000)

    def __init__(self, camera_id: str = "camera-01"):
        self.camera_id = camera_id
        self._audio_buffer: deque = deque(maxlen=self.SAMPLE_RATE * 5)
        self._last_event_time: dict[str, float] = {}
        self._event_cooldown = 10.0

    def feed_audio(self, audio_data: bytes | np.ndarray, sample_rate: int = None):
        """Feed raw audio data into the detector."""
        if isinstance(audio_data, (bytes, bytearray)):
            audio = np.frombuffer(audio_data, dtype=np.int16)
        elif isinstance(audio_data, np.ndarray):
            audio = audio_data.astype(np.int16)
        else:
            return

        if sample_rate and sample_rate != self.SAMPLE_RATE:
            from scipy import signal as sp_signal
            try:
                audio = sp_signal.resample(audio, int(len(audio) * self.SAMPLE_RATE / sample_rate))
            except ImportError:
                pass

        audio = audio.astype(np.float32) / 32768.0
        self._audio_buffer.extend(audio.tolist())

    def _compute_spectrogram(self, audio: np.ndarray, n_fft: int = None, hop: int = None):
        if n_fft is None:
            n_fft = self.N_FFT
        if hop is None:
            hop = self.HOP_LENGTH

        if len(audio) < n_fft:
            return np.zeros((n_fft // 2, 1)), np.array([0])

        n_frames = (len(audio) - n_fft) // hop + 1
        if n_frames <= 0:
            return np.zeros((n_fft // 2, 1)), np.array([0])

        spectrogram = np.zeros((n_fft // 2, n_frames))
        for i in range(n_frames):
            start = i * hop
            frame = audio[start:start + n_fft] * np.hanning(n_fft)
            spectrum = np.abs(np.fft.rfft(frame))
            spectrogram[:, i] = spectrum

        freqs = np.fft.rfftfreq(n_fft, d=1.0 / self.SAMPLE_RATE)
        times = np.arange(n_frames) * hop / self.SAMPLE_RATE
        return spectrogram, times, freqs

    def _compute_db_spectrum(self, spectrogram: np.ndarray):
        with np.errstate(divide='ignore'):
            db = 20 * np.log10(spectrogram + 1e-10)
        return db

    def _band_energy(self, db_spectrum: np.ndarray, freqs: np.ndarray, fmin: float, fmax: float):
        mask = (freqs >= fmin) & (freqs <= fmax)
        if not np.any(mask):
            return np.zeros(db_spectrum.shape[1])
        band = db_spectrum[mask, :]
        return np.mean(band, axis=0)

    def detect_events(self) -> list[DetectionEvent]:
        """Analyze buffered audio and detect events."""
        events = []
        if len(self._audio_buffer) < self.SAMPLE_RATE:
            return events

        audio = np.array(list(self._audio_buffer))
        spectrogram, times, freqs = self._compute_spectrogram(audio)
        db_spectrum = self._compute_db_spectrum(spectrogram)

        now = time.time()
        timestamp = datetime.now(timezone.utc).isoformat()

        gunshot = self._detect_gunshot(db_spectrum, freqs, times, now)
        if gunshot:
            events.append(self._build_audio_event("gunshot", gunshot, timestamp))

        glass = self._detect_glass_break(db_spectrum, freqs, times, now)
        if glass:
            events.append(self._build_audio_event("glass_break", glass, timestamp))

        scream = self._detect_scream(db_spectrum, freqs, times, now)
        if scream:
            events.append(self._build_audio_event("scream", scream, timestamp))

        bang = self._detect_loud_bang(db_spectrum, freqs, times, now)
        if bang:
            events.append(self._build_audio_event("loud_bang", bang, timestamp))

        self._audio_buffer.clear()
        return events

    def _detect_gunshot(self, db_spectrum, freqs, times, now):
        band = self._band_energy(db_spectrum, freqs, *self.GUNSHOT_FREQ_RANGE)
        if len(band) == 0:
            return None
        peak_db = np.max(band)
        if peak_db < self.GUNSHOT_DB_THRESHOLD:
            return None
        peak_idx = np.argmax(band)
        duration_ms = (times[peak_idx] - times[0]) * 1000 if len(times) > peak_idx else 0
        if not (self.GUNSHOT_DURATION_MS[0] <= duration_ms <= self.GUNSHOT_DURATION_MS[1]):
            duration_check = True
        if not self._check_cooldown("gunshot", now):
            return None
        return {"confidence": min(peak_db / 40.0, 0.98), "duration_ms": duration_ms}

    def _detect_glass_break(self, db_spectrum, freqs, times, now):
        band = self._band_energy(db_spectrum, freqs, *self.GLASS_BREAK_FREQ_RANGE)
        if len(band) == 0:
            return None
        peak_db = np.max(band)
        if peak_db < self.GLASS_BREAK_DB_THRESHOLD:
            return None
        if not self._check_cooldown("glass_break", now):
            return None
        peak_idx = np.argmax(band)
        sustained = np.mean(band > (peak_db - 5)) > 0.3
        return {"confidence": min(peak_db / 35.0, 0.95), "sustained": sustained}

    def _detect_scream(self, db_spectrum, freqs, times, now):
        band = self._band_energy(db_spectrum, freqs, *self.SCREAM_FREQ_RANGE)
        if len(band) == 0:
            return None
        peak_db = np.max(band)
        if peak_db < self.SCREAM_DB_THRESHOLD:
            return None
        if not self._check_cooldown("scream", now):
            return None
        above_threshold = np.sum(band > self.SCREAM_DB_THRESHOLD) / len(band)
        if above_threshold < 0.5:
            return None
        return {"confidence": min(peak_db / 40.0, 0.98), "duration_ratio": above_threshold}

    def _detect_loud_bang(self, db_spectrum, freqs, times, now):
        band = self._band_energy(db_spectrum, freqs, *self.BANG_FREQ_RANGE)
        if len(band) == 0:
            return None
        global_max = np.max(db_spectrum)
        if global_max < self.BANG_DB_THRESHOLD:
            return None
        if not self._check_cooldown("loud_bang", now):
            return None
        return {"confidence": min(global_max / 45.0, 0.95), "peak_db": global_max}

    def _check_cooldown(self, event_type: str, now: float) -> bool:
        key = f"audio:{event_type}"
        last = self._last_event_time.get(key, 0)
        if now - last < self._event_cooldown:
            return False
        self._last_event_time[key] = now
        return True

    def _build_audio_event(self, event_type, metadata, timestamp):
        return DetectionEvent(
            event_id=f"audio-{event_type}-{int(time.time() * 1000)}",
            camera_id=self.camera_id,
            timestamp=timestamp,
            event_type="anomaly",
            entity_type="object",
            bbox={"x": 0, "y": 0, "w": 0, "h": 0},
            confidence=metadata["confidence"],
            track_id="",
            anomaly_label=event_type,
            source_repo="audio-analysis",
            requires_authorization=False,
        )


def main():
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    camera_id = os.getenv("CAMERA_ID", "camera-01")
    video_source = os.getenv(
        "VIDEO_SOURCE",
        os.path.join(os.path.dirname(__file__), "..", "..", "test_feeds", "camera01.mp4"),
    )
    adapter = AnomalyAdapter(camera_id=camera_id)
    cap = cv2.VideoCapture(video_source)
    if not cap.isOpened():
        logger.error("Cannot open video source: %s", video_source)
        sys.exit(1)
    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                continue
            events = adapter.process(frame)
            if events:
                adapter.publish_batch(events)
                for e in events:
                    logger.info("Anomaly: %s on %s", e.anomaly_label, e.camera_id)
    except KeyboardInterrupt:
        logger.info("Interrupted")
    finally:
        cap.release()


if __name__ == "__main__":
    main()

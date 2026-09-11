"""
Audio Event Detection Module
==============================
Detects audio events (gunshot, glass break, scream, loud bang) using
spectral analysis techniques.

Inspired by Sentigon's audio event detection (PANNs/YAMNet)
and OpenDVR's audio analysis pipeline.
"""
import time
import logging
import numpy as np
from collections import deque
from datetime import datetime, timezone

logger = logging.getLogger("prahari.audio")


class AudioEventDetector:
    """
    Detects audio events using spectral analysis.
    No external dependencies beyond numpy (scipy optional for resampling).
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
        self._last_event_time: dict = {}
        self._event_cooldown = 10.0

    def feed_audio(self, audio_data, sample_rate=None):
        """Feed raw audio data into the detector."""
        if isinstance(audio_data, (bytes, bytearray)):
            audio = np.frombuffer(audio_data, dtype=np.int16)
        elif isinstance(audio_data, np.ndarray):
            audio = audio_data.astype(np.int16)
        else:
            return

        if sample_rate and sample_rate != self.SAMPLE_RATE:
            try:
                from scipy import signal as sp_signal
                audio = sp_signal.resample(
                    audio, int(len(audio) * self.SAMPLE_RATE / sample_rate)
                )
            except ImportError:
                pass

        audio = audio.astype(np.float32) / 32768.0
        self._audio_buffer.extend(audio.tolist())

    def _compute_spectrogram(self, audio, n_fft=None, hop=None):
        if n_fft is None:
            n_fft = self.N_FFT
        if hop is None:
            hop = self.HOP_LENGTH

        if len(audio) < n_fft:
            return np.zeros((n_fft // 2 + 1, 1)), np.array([0]), np.array([0])

        n_frames = (len(audio) - n_fft) // hop + 1
        if n_frames <= 0:
            return np.zeros((n_fft // 2 + 1, 1)), np.array([0]), np.array([0])

        spectrogram = np.zeros((n_fft // 2 + 1, n_frames))
        for i in range(n_frames):
            start = i * hop
            frame = audio[start:start + n_fft] * np.hanning(n_fft)
            spectrum = np.abs(np.fft.rfft(frame))
            spectrogram[:, i] = spectrum

        freqs = np.fft.rfftfreq(n_fft, d=1.0 / self.SAMPLE_RATE)
        times = np.arange(n_frames) * hop / self.SAMPLE_RATE
        return spectrogram, times, freqs

    def _compute_db_spectrum(self, spectrogram):
        with np.errstate(divide='ignore'):
            db = 20 * np.log10(spectrogram + 1e-10)
        return db

    def _band_energy(self, db_spectrum, freqs, fmin, fmax):
        mask = (freqs >= fmin) & (freqs <= fmax)
        if not np.any(mask):
            return np.zeros(db_spectrum.shape[1])
        band = db_spectrum[mask, :]
        return np.mean(band, axis=0)

    def detect_events(self):
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
            events.append({
                "event_id": f"audio-gunshot-{int(time.time() * 1000)}",
                "camera_id": self.camera_id,
                "timestamp": timestamp,
                "event_type": "anomaly",
                "entity_type": "object",
                "bbox": {"x": 0, "y": 0, "w": 0, "h": 0},
                "confidence": gunshot["confidence"],
                "track_id": "",
                "anomaly_label": "gunshot",
                "source_repo": "audio-analysis",
                "requires_authorization": False,
            })

        glass = self._detect_glass_break(db_spectrum, freqs, times, now)
        if glass:
            events.append({
                "event_id": f"audio-glass_break-{int(time.time() * 1000)}",
                "camera_id": self.camera_id,
                "timestamp": timestamp,
                "event_type": "anomaly",
                "entity_type": "object",
                "bbox": {"x": 0, "y": 0, "w": 0, "h": 0},
                "confidence": glass["confidence"],
                "track_id": "",
                "anomaly_label": "glass_break",
                "source_repo": "audio-analysis",
                "requires_authorization": False,
            })

        scream = self._detect_scream(db_spectrum, freqs, times, now)
        if scream:
            events.append({
                "event_id": f"audio-scream-{int(time.time() * 1000)}",
                "camera_id": self.camera_id,
                "timestamp": timestamp,
                "event_type": "anomaly",
                "entity_type": "object",
                "bbox": {"x": 0, "y": 0, "w": 0, "h": 0},
                "confidence": scream["confidence"],
                "track_id": "",
                "anomaly_label": "scream",
                "source_repo": "audio-analysis",
                "requires_authorization": False,
            })

        bang = self._detect_loud_bang(db_spectrum, freqs, times, now)
        if bang:
            events.append({
                "event_id": f"audio-loud_bang-{int(time.time() * 1000)}",
                "camera_id": self.camera_id,
                "timestamp": timestamp,
                "event_type": "anomaly",
                "entity_type": "object",
                "bbox": {"x": 0, "y": 0, "w": 0, "h": 0},
                "confidence": bang["confidence"],
                "track_id": "",
                "anomaly_label": "loud_bang",
                "source_repo": "audio-analysis",
                "requires_authorization": False,
            })

        self._audio_buffer.clear()
        return events

    def _detect_gunshot(self, db_spectrum, freqs, times, now):
        band = self._band_energy(db_spectrum, freqs, *self.GUNSHOT_FREQ_RANGE)
        if len(band) == 0:
            return None
        peak_db = np.max(band)
        if peak_db < self.GUNSHOT_DB_THRESHOLD:
            return None
        if not self._check_cooldown("gunshot", now):
            return None
        return {"confidence": min(peak_db / 40.0, 0.98)}

    def _detect_glass_break(self, db_spectrum, freqs, times, now):
        band = self._band_energy(db_spectrum, freqs, *self.GLASS_BREAK_FREQ_RANGE)
        if len(band) == 0:
            return None
        peak_db = np.max(band)
        if peak_db < self.GLASS_BREAK_DB_THRESHOLD:
            return None
        if not self._check_cooldown("glass_break", now):
            return None
        return {"confidence": min(peak_db / 35.0, 0.95)}

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
        return {"confidence": min(peak_db / 40.0, 0.98)}

    def _detect_loud_bang(self, db_spectrum, freqs, times, now):
        global_max = np.max(db_spectrum)
        if global_max < self.BANG_DB_THRESHOLD:
            return None
        if not self._check_cooldown("loud_bang", now):
            return None
        return {"confidence": min(global_max / 45.0, 0.95)}

    def _check_cooldown(self, event_type, now):
        key = f"audio:{event_type}"
        last = self._last_event_time.get(key, 0)
        if now - last < self._event_cooldown:
            return False
        self._last_event_time[key] = now
        return True

"""Primary window arithmetic shared by synchronous acquisition and private worker tests."""
from collections import deque

import numpy as np
from cyton_fatigue import PHYSICAL_INDICES, WINDOW_SAMPLES
from cyton_covariance import WINDOW_SAMPLES as COVARIANCE_SAMPLES
from cyton_sqi import CytonSQIMonitor
from processing_diagnostics import processing_snapshot

FATIGUE_MODEL_CHANNEL_MAP = ("FT7", "FT8", "CP1", "CP2", "P1", "P2", "O1", "O2")


class PrimaryWindowProcessor:
    def __init__(self, sqi_monitor, four_channel_fatigue, covariance_model,
                 covariance_stream, emotion_model, emotion_disabled, engine,
                 channel_map, scale, filter_backend, snapshot, descriptors):
        self.sqi_monitor = sqi_monitor
        self.four_channel_fatigue = four_channel_fatigue
        self.covariance_model = covariance_model
        self.covariance_stream = covariance_stream
        self.emotion_model = emotion_model
        self.emotion_disabled = emotion_disabled
        self.engine = engine
        self.channel_map = channel_map
        self.scale = scale
        self.filter_backend = filter_backend
        self.snapshot = snapshot
        self.descriptors = descriptors
        self.rows = deque(maxlen=WINDOW_SAMPLES)
        self.filtered_rows = deque(maxlen=WINDOW_SAMPLES)
        self.bad_rows = deque(maxlen=WINDOW_SAMPLES)
        self.covariance_bad_rows = deque(maxlen=COVARIANCE_SAMPLES)
        self.covariance_pending = []
        self.fatigue_pending = []
        self.windows = self.clipped_rows = 0
        self.reset_stream(clear_filters=False)

    @property
    def calibration_progress(self):
        if self.four_channel_fatigue is not None:
            return len(self.four_channel_fatigue.baseline)
        count = WINDOW_SAMPLES // self.sqi_monitor.segment_samples
        return sorted((min(15, len(r) // count) for r in
                       self.sqi_monitor.reference), reverse=True)[5]

    def reset_stream(self, *, clear_filters=True):
        if clear_filters and self.covariance_stream is not None:
            self.covariance_stream.reset()
        if clear_filters and self.four_channel_fatigue is not None:
            self.four_channel_fatigue.reset_stream()
        for rows in (self.rows, self.filtered_rows, self.bad_rows,
                     self.covariance_bad_rows, self.covariance_pending,
                     self.fatigue_pending):
            rows.clear()
        self.new_samples = self.fatigue_new_samples = 0
        self.stream_samples = 0
        self.fatigue_feature_end = None
        self.last_fatigue_result = None
        self.last_sqi = self.last_emotion = self.last_raw_interference = None
        self.calibration_ready = bool(self.four_channel_fatigue is not None
                                      and self.four_channel_fatigue.mean is not None)

    def new_wearing(self):
        self.sqi_monitor = CytonSQIMonitor(calibration_windows=15, sample_rate_hz=250)
        if self.four_channel_fatigue is not None:
            self.four_channel_fatigue.reset()
        self.reset_stream()

    def append(self, raw, filtered_uv, sample_bad, counters):
        self.stream_samples += 1
        self.rows.append(raw.copy())
        self.filtered_rows.append(filtered_uv)
        self.bad_rows.append(sample_bad)
        if self.four_channel_fatigue is not None:
            self.fatigue_pending.append(filtered_uv)
            self.fatigue_new_samples += 1
            if len(self.fatigue_pending) == 125:
                self.four_channel_fatigue.append(np.asarray(self.fatigue_pending))
                self.fatigue_pending.clear()
        if self.covariance_stream is not None:
            self.covariance_pending.append(filtered_uv)
            if len(self.covariance_pending) == 125:
                self.covariance_stream.append(np.asarray(self.covariance_pending))
                self.covariance_pending.clear()
            self.covariance_bad_rows.append(sample_bad)
        self.new_samples += 1
        hop = 500 if self.calibration_ready else WINDOW_SAMPLES
        if len(self.rows) < WINDOW_SAMPLES or self.new_samples < hop:
            return None
        return self.evaluate(counters)

    def evaluate(self, counters):
        packets_seen = counters["packets_seen"]
        dropped_packets = counters["dropped_packets"]
        sequence_gaps = counters["sequence_gaps"]
        unresolved_gaps = counters["unresolved_gaps"]
        malformed_bytes = counters["malformed_bytes"]
        window_counts, raw_window_uv, window_uv = self.snapshot(
            self.rows, self.filtered_rows, self.scale)
        raw_descriptors = self.descriptors(raw_window_uv, self.sqi_monitor.segment_samples)
        self.last_raw_interference = {
            "mains_ratio": np.max(raw_descriptors[:, :, 4], axis=0).round(6).tolist(),
            "p99_abs_uv": np.max(raw_descriptors[:, :, 1], axis=0).round(3).tolist(),
            "above_transport_ratio": np.mean(
                np.abs(raw_window_uv) > 327.67, axis=0).round(6).tolist(),
            "adc_near_rail_ratio": np.mean(
                np.abs(window_counts) >= 0.95 * (2**23 - 1), axis=0).round(6).tolist(),
        }
        units = np.rint(window_uv * 100.0)
        in_range = np.isfinite(units) & (units >= -32768) & (units <= 32767)
        outside_rows = ~np.all(in_range, axis=1)
        channel_transport_ok = np.all(in_range, axis=0) & (not any(self.bad_rows))
        clipped_now = int(np.count_nonzero(outside_rows))
        self.clipped_rows += clipped_now
        safe_units = np.where(np.isfinite(units), units, 0)
        window_i16 = np.clip(safe_units, -32768, 32767).astype(np.int16)
        transport_ok = not any(self.bad_rows) and clipped_now == 0
        self.last_sqi = self.sqi_monitor.process(window_uv, transport_ok=channel_transport_ok)
        if self.covariance_model is not None:
            try:
                indexes = self.covariance_stream.indexes
                quality = [self.last_sqi["channels"][i]["quality"]
                           if self.last_sqi["channels"][i]["calibrated"] else 0.0
                           for i in indexes]
                if not self.covariance_stream.ready:
                    self.last_emotion = self.covariance_model.predict(self.covariance_stream, quality)
                elif any(self.covariance_bad_rows):
                    self.last_emotion = {"valid": False, "state": "packet_gap_12s"}
                else:
                    self.last_emotion = self.covariance_model.predict(self.covariance_stream, quality)
                self.last_emotion["channel_map"] = list(self.covariance_model.metadata["channels"])
                if sum(self.last_sqi["channels"][i]["calibrated"] for i in indexes) < 6:
                    self.last_emotion["valid"] = False
                    self.last_emotion["state"] = "sqi_calibrating"
            except Exception as exc:
                self.last_emotion = {"valid": False, "state": "error",
                                "reason": type(exc).__name__, "detail": str(exc)}
        elif self.emotion_model is not None:
            try:
                self.last_emotion = self.emotion_model.predict(
                    window_uv,
                    [c["quality"] if c["calibrated"] else 0.0 for c in self.last_sqi["channels"]],
                    source_rate_hz=250, source_channel_map=self.channel_map)
                self.last_emotion["channel_map"] = self.emotion_model.model["channels"]
                model_indexes = self.emotion_model.channel_indices(self.channel_map)
                if sum(self.last_sqi["channels"][i]["calibrated"] for i in model_indexes) < self.emotion_model.minimum_usable:
                    self.last_emotion["valid"] = False
                    self.last_emotion["state"] = "sqi_calibrating"
            except Exception as exc:
                self.last_emotion = {
                    "valid": False, "state": "error",
                    "reason": type(exc).__name__, "detail": str(exc),
                }
        else:
            self.last_emotion = dict(self.emotion_disabled or {
                "valid": False, "state": "model_unavailable",
            })
        if self.four_channel_fatigue is not None:
            required = [self.last_sqi["channels"][i] for i in PHYSICAL_INDICES]
            required_quality_ok = all(item["quality"] >= 0.5 for item in required)
            required_transport_ok = bool(np.all(channel_transport_ok[list(PHYSICAL_INDICES)]))
            if self.fatigue_new_samples >= WINDOW_SAMPLES:
                if self.fatigue_pending:
                    self.four_channel_fatigue.append(np.asarray(self.fatigue_pending))
                    self.fatigue_pending.clear()
                self.last_fatigue_result = self.four_channel_fatigue.process_window(
                    required_quality_ok, required_transport_ok)
                self.fatigue_feature_end = packets_seen
                self.fatigue_new_samples = 0
            result = dict(self.last_fatigue_result or {
                "valid": False, "state": "INVALID", "reason": "FEATURE_WARMUP",
                "calibration_current": 0, "calibration_total": 15,
            })
            result["last_inference_window"] = result.get("window", 0)
            result["window"] = self.windows + 1
            result["window_hop_seconds"] = 8
            result["algorithm_version"] = "seedvig-cyton-overlap4-arm-v1"
            if result.get("state") in ("NORMAL", "MILD", "SEVERE"):
                if not required_quality_ok or not required_transport_ok:
                    result.update(valid=False, state="INVALID",
                                  reason=("TRANSPORT" if not required_transport_ok
                                          else "REQUIRED_CHANNEL_QUALITY"))
                elif not all(item["calibrated"] for item in required):
                    result.update(valid=False, state="INVALID",
                                  reason="REQUIRED_CHANNEL_SQI_CALIBRATING")
        elif self.engine is None:
            result = {
                "window": self.windows + 1,
                "valid": False,
                "state": "INVALID",
                "reason": "CHANNEL_MAP_MISMATCH",
                "detail": "Fatigue model requires " + ",".join(FATIGUE_MODEL_CHANNEL_MAP),
                "calibration_current": self.last_sqi["calibration_current"],
                "calibration_total": self.last_sqi["calibration_total"],
            }
        else:
            try:
                result = self.engine.process_window(window_i16, transport_ok=transport_ok)
            except RuntimeError as exc:
                if not str(exc).startswith("PL DE invalid result:"):
                    raise
                result = {
                    "window": self.engine.window_index,
                    "valid": False,
                    "state": "INVALID",
                    "reason": "SIGNAL_SATURATION",
                    "detail": str(exc),
                    "calibration_current": len(self.engine.baseline),
                    "calibration_total": 15,
                }
        self.windows += 1
        self.new_samples = 0
        self.calibration_ready = bool(result.get("calibration_ready")) or self.calibration_ready
        result.update(source="cyton_usb", packets_seen=packets_seen,
                      filter_backend=self.filter_backend,
                      dropped_packets=dropped_packets,
                      sequence_gaps=sequence_gaps, unresolved_gaps=unresolved_gaps,
                      malformed_bytes=malformed_bytes,
                      clipped_rows=self.clipped_rows, sqi=self.last_sqi,
                      raw_interference=self.last_raw_interference,
                      emotion=self.last_emotion,
                      channel_map=list(self.channel_map),
                      signal_quality=self.last_sqi["state"])
        result['calibration_retained'] = bool(np.any(self.sqi_monitor.calibrated_channels))
        result['processing'] = processing_snapshot(self.stream_samples,packets_seen,self.windows,
            self.covariance_model,self.four_channel_fatigue,
            bool(self.last_emotion and self.last_emotion.get('valid')),
            result.get('state') in ('CALIBRATING','NORMAL','MILD','SEVERE') and result.get('valid') is True,
            fatigue_feature_end=self.fatigue_feature_end)
        return result

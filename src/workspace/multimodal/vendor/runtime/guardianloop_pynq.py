"""PYNQ adapter for the existing GuardianLoop Z15 EEG PL design.

One input is a complete 2000 x 8 window in the transport's signed-int16 unit
(0.01 microvolt/LSB). This module deliberately does not ingest UART/LSL or
drive the ESP32 alarm: it keeps the established PL/PS fatigue contract separate
from transport and actuation.
"""

import math
from collections import deque
from pathlib import Path
from time import monotonic, sleep

import numpy as np
from pynq import Overlay, allocate


WINDOW_SAMPLES = 2000
CHANNELS = 8
FEATURES = 40
BASELINE_WINDOWS = 15
EMA_ALPHA = 0.25
DE_BUILD_ID = 0x44453031
HGB_BUILD_ID = 0x48473031
HGB_MODEL_ID = 0x50537911
HGB_THRESHOLD0 = 0.34379776424076558
HGB_THRESHOLD1 = 0.66079422849339409


def _signed(value, bits):
    return value - (1 << bits) if value & (1 << (bits - 1)) else value


def _q24(value):
    if not math.isfinite(value):
        raise ValueError("Non-finite calibrated feature")
    scaled = value * 16777216.0
    if scaled >= 2147483647:
        return 0x7FFFFFFF
    if scaled <= -2147483648:
        return 0x80000000
    rounded = math.floor(scaled + 0.5) if scaled >= 0 else math.ceil(scaled - 0.5)
    return rounded & 0xFFFFFFFF


def _u64(ip, low, high):
    return (int(ip.read(high)) << 32) | int(ip.read(low))


def _poll(ip, offset, mask, expected, seconds=1.0):
    deadline = monotonic() + seconds
    while monotonic() < deadline:
        status = int(ip.read(offset))
        if status & mask == expected:
            return status
        sleep(0.001)
    raise TimeoutError(f"PL register 0x{offset:02X} did not reach 0x{expected:X}")


class GuardianLoopPynq:
    def __init__(self, bitfile=None, download=True):
        bitfile = Path(bitfile) if bitfile else Path(__file__).with_name("guardianloop_pynq.bit")
        self.overlay = Overlay(str(bitfile), download=download)
        self.dma = self.overlay.axi_dma_0
        self.quality = self.overlay.guardianloop_eeg_quality_v0_0
        self.de = self.overlay.guardianloop_eeg_de_accel_v0_0
        self.hgb = self.overlay.guardianloop_hgb_accel_v0_0
        self.window_index = 0
        self.baseline = []
        self.mean = None
        self.scale = None
        self.feature_ema = None
        self.recent_perclos = deque(maxlen=3)
        self._dma_stalled = False
        self._stalled_buffer = None

        if int(self.de.read(0x20)) != DE_BUILD_ID:
            raise RuntimeError("Wrong PL DE build ID")
        if (int(self.hgb.read(0x18)), int(self.hgb.read(0x30))) != (HGB_BUILD_ID, HGB_MODEL_ID):
            raise RuntimeError("Wrong PL HGB build/model ID")
        if (int(self.hgb.read(0x20)), int(self.hgb.read(0x24)),
            int(self.hgb.read(0x28)), int(self.hgb.read(0x2C))) != (3480, 120, 24, 30):
            raise RuntimeError("PL HGB register/model ABI mismatch")
        if not hasattr(self.dma, "sendchannel"):
            raise RuntimeError("The GuardianLoop MM2S DMA channel is unavailable")

        self.de.write(0x04, WINDOW_SAMPLES)
        self.de.write(0x00, 0x31)  # enable + clear stats + reset causal IIR state
        _poll(self.de, 0x08, 0x06, 0)
        self.hgb.write(0x00, 0x02)  # clear stale feature/result state
        if int(self.hgb.read(0x04)) & 0x07:
            raise RuntimeError("PL HGB did not clear")

    def _configure_quality(self):
        # Match the existing bare-metal engineering thresholds, not a clinical gate.
        for offset, value in (
            (0x00, 0x1F), (0x04, WINDOW_SAMPLES), (0x08, WINDOW_SAMPLES),
            (0x0C, 10000), (0x10, 0), (0x14, 4000), (0x18, 0xFF),
        ):
            self.quality.write(offset, value)

    def _wait_dma_send(self, seconds=2.0):
        deadline = monotonic() + seconds
        while monotonic() < deadline:
            status = int(self.dma.mmio.read(0x04))
            if status & 0x70:
                raise RuntimeError(f"AXI DMA MM2S error: DMASR=0x{status:08X}")
            if status & 0x02:
                return
            sleep(0.001)
        raise TimeoutError("AXI DMA MM2S did not become idle within 2 seconds")

    def _read_de(self):
        _poll(self.de, 0x08, 0x04, 0x04)
        status = int(self.de.read(0x08))
        completed = int(self.de.read(0x24))
        saturation = int(self.de.read(0x2C))
        if completed != WINDOW_SAMPLES or saturation or status & 0x08:
            # A saturated window must not poison the next causal-filter window.
            self.de.write(0x00, 0x31)  # enable + clear stats + reset IIR state
            _poll(self.de, 0x08, 0x06, 0)
            raise RuntimeError(
                f"PL DE invalid result: samples={completed} saturation={saturation} status=0x{status:X}"
            )
        values = np.empty(FEATURES, dtype=np.float64)
        for index in range(FEATURES):
            self.de.write(0x0C, index)
            sum_q8 = _signed(_u64(self.de, 0x10, 0x14), 64)
            sumsq_q16 = _u64(self.de, 0x18, 0x1C)
            mean_q8 = sum_q8 / WINDOW_SAMPLES
            variance_q16 = sumsq_q16 / WINDOW_SAMPLES - mean_q8 * mean_q8
            variance = max(variance_q16 / 65536.0, 1.0e-12)
            values[index] = 0.5 * math.log(17.079468445347132 * variance)
        if not np.all(np.isfinite(values)):
            raise RuntimeError("Non-finite PL DE features")
        sequence = int(self.de.read(0x28))
        self.de.write(0x00, 0x11)  # enable + clear per-window stats, retain IIR state
        _poll(self.de, 0x08, 0x06, 0)
        return values, sequence

    def predict_features(self, features):
        """Run an already calibrated 40-feature vector through the existing PL HGB."""
        feature_vector = np.asarray(features, dtype=np.float64)
        if feature_vector.shape != (FEATURES,):
            raise ValueError("Expected 40 calibrated features")
        for index, value in enumerate(feature_vector):
            self.hgb.write(0x08, index)
            self.hgb.write(0x0C, _q24(float(value)))
        status = int(self.hgb.read(0x04))
        if not status & 0x08 or status & 0x05:
            raise RuntimeError(f"PL HGB features not ready: status=0x{status:X}")
        self.hgb.write(0x00, 0x01)
        deadline = monotonic() + 1.0
        while monotonic() < deadline:
            status = int(self.hgb.read(0x04))
            if status & 0x04:
                raise RuntimeError(f"PL HGB error: status=0x{status:X}")
            if status & 0x02 and not status & 0x01:
                break
            sleep(0.001)
        else:
            raise TimeoutError("PL HGB inference did not complete")
        perclos = _signed(int(self.hgb.read(0x10)), 32) / 1073741824.0
        level = int(self.hgb.read(0x14))
        if not 0.0 <= perclos <= 1.0 or level not in (0, 1, 2):
            raise RuntimeError("PL HGB returned out-of-range result")
        return {"perclos": perclos, "level": level, "cycles": int(self.hgb.read(0x1C))}

    def process_window(self, samples, transport_ok=True):
        """Process exactly one complete 8-second window; never actuates an alarm."""
        if not self.overlay.is_loaded():
            raise RuntimeError("GuardianLoop Overlay was replaced; restart the PYNQ server")
        if self._dma_stalled:
            raise RuntimeError("DMA is locked after a prior failure; restart the PYNQ server")
        self.window_index += 1
        result = {"window": self.window_index, "valid": False, "state": "INVALID",
                  "calibration_current": len(self.baseline),
                  "calibration_total": BASELINE_WINDOWS}
        if not transport_ok:
            result["reason"] = "TRANSPORT"
            return result
        source = np.asarray(samples)
        if source.shape != (WINDOW_SAMPLES, CHANNELS) or source.dtype != np.int16:
            raise ValueError("Expected exactly 2000 x 8 signed-int16 EEG samples")
        if source.nbytes != 32000:
            raise ValueError("Wrong EEG window byte length")

        buffer = allocate(shape=(WINDOW_SAMPLES, CHANNELS), dtype=np.int16)
        transfer_started = False
        transfer_complete = False
        try:
            buffer[:] = source
            buffer.flush()
            self._configure_quality()
            self.dma.sendchannel.transfer(buffer)
            transfer_started = True
            self._wait_dma_send()
            transfer_complete = True
        except Exception:
            if transfer_started and not transfer_complete:
                self._dma_stalled = True
                self._stalled_buffer = buffer  # DMA may still reference this CMA memory.
            raise
        finally:
            if not transfer_started or transfer_complete:
                buffer.close()

        _poll(self.quality, 0x20, 0x04, 0x04)
        quality_status = int(self.quality.read(0x20))
        valid_mask = int(self.quality.read(0x24))
        reason = int(self.quality.read(0x28))
        result.update(quality_status=quality_status, valid_mask=valid_mask, reason_code=reason)
        # DE runs for every streamed window, including invalid ones, keeping causal state.
        features, sequence = self._read_de()
        result["de_window_sequence"] = sequence
        if not quality_status & 0x02 or valid_mask != 0xFF or reason != 0:
            result["reason"] = "SIGNAL_QUALITY"
            return result

        if self.mean is None:
            self.baseline.append(features)
            count = len(self.baseline)
            result.update(valid=True, state="CALIBRATING", calibration_current=count)
            if count == BASELINE_WINDOWS:
                baseline = np.stack(self.baseline)
                self.mean = baseline.mean(axis=0)
                self.scale = baseline.std(axis=0, ddof=0)
                self.scale[self.scale < 1.0e-6] = 1.0
                result["calibration_ready"] = True
            return result

        calibrated = (features - self.mean) / self.scale
        if not np.all(np.isfinite(calibrated)):
            result["reason"] = "CALIBRATION_NUMERICAL"
            return result
        if self.feature_ema is None:
            self.feature_ema = calibrated.copy()
        else:
            self.feature_ema = EMA_ALPHA * calibrated + (1.0 - EMA_ALPHA) * self.feature_ema
        raw = self.predict_features(self.feature_ema)
        self.recent_perclos.append(raw["perclos"])
        smoothed = sum(self.recent_perclos) / len(self.recent_perclos)
        level = 0 if smoothed < HGB_THRESHOLD0 else (1 if smoothed < HGB_THRESHOLD1 else 2)
        result.update(valid=True, state=("NORMAL", "MILD", "SEVERE")[level],
                      level=level, perclos=raw["perclos"], smoothed_perclos=smoothed,
                      hgb_cycles=raw["cycles"], calibration_current=BASELINE_WINDOWS)
        return result

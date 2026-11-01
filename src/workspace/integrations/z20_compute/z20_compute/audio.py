"""PCM, one-second sound features and immutable DAC blocks with scan sync."""
from dataclasses import dataclass
import numpy as np

SAMPLE_RATE = 16000
FFT_SIZE = 1024
SOUND_LABELS = ("clap", "whistle", "knock")


def _pcm(samples):
    samples = np.asarray(samples, dtype=np.float64)
    if samples.ndim != 1 or not len(samples) or not np.isfinite(samples).all():
        raise ValueError("expected finite mono PCM")
    return samples


def spectrum(samples, sample_rate=SAMPLE_RATE):
    samples = _pcm(samples)
    if type(sample_rate) is not int or sample_rate <= 0 or len(samples) < 4:
        raise ValueError("invalid spectrum sampling parameters")
    window = np.hanning(len(samples))
    amplitude = np.abs(np.fft.rfft((samples-samples.mean())*window))*2/window.sum()
    amplitude[0] *= .5
    if len(samples) % 2 == 0:
        amplitude[-1] *= .5
    return np.fft.rfftfreq(len(samples), 1/sample_rate), amplitude


def sound_features(samples, sample_rate=SAMPLE_RATE):
    samples = _pcm(samples)
    if sample_rate != SAMPLE_RATE or len(samples) != SAMPLE_RATE:
        raise ValueError("sound model expects one second of 16kHz mono PCM")
    samples = samples - samples.mean()
    rms = float(np.sqrt(np.mean(samples*samples)))
    if rms < 1e-4:
        raise ValueError("silence")
    if np.max(np.abs(samples)) > 1.05:
        raise ValueError("PCM outside calibrated full scale")
    # NumPy 1.17 on the ARM image has no sliding_window_view. Explicit copies
    # retain exactly the same 30 windows without exposing unsafe strided views.
    frames = np.stack([samples[start:start+FFT_SIZE]
                       for start in range(0, len(samples)-FFT_SIZE+1, 512)])
    power = np.abs(np.fft.rfft(frames*np.hanning(FFT_SIZE), axis=1))**2
    # Twenty fixed linear bands. Exported preprocessing is identical on PC/ARM.
    edges = np.linspace(0, power.shape[1], 21, dtype=int)
    bands = np.stack([np.log(np.maximum(power[:, a:b].mean(axis=1), 1e-12))
                      for a, b in zip(edges[:-1], edges[1:])], axis=1)
    return np.r_[bands.mean(axis=0), bands.std(axis=0)].astype(np.float32)


def adc_to_pcm(codes, *, zero_code=128., counts_per_full_scale=128.):
    codes = np.asarray(codes)
    if codes.dtype != np.uint8 or codes.ndim != 1 or counts_per_full_scale <= 0:
        raise ValueError("expected unsigned eight-bit ADC data and calibrated scale")
    return (codes.astype(np.float64)-zero_code)/counts_per_full_scale


def resample_audio(samples, source_rate, target_rate=SAMPLE_RATE):
    from math import gcd
    from scipy import signal
    if type(source_rate) is not int or source_rate <= 0:
        raise ValueError("invalid ADC sample rate")
    divisor = gcd(source_rate, target_rate)
    return signal.resample_poly(_pcm(samples), target_rate//divisor, source_rate//divisor)


@dataclass(frozen=True)
class DacBlock:
    mode: str
    codes: np.ndarray
    sync: np.ndarray
    output_rate_hz: int
    frequency_step_hz: float = 0.


class DacOutput:
    """Block construction only; hardware owns continuous clock and mode commit."""
    def __init__(self):
        self.fir, self.delay = None, None

    def reset(self):
        self.fir, self.delay = None, None

    def audio(self, samples, sample_rate=SAMPLE_RATE, *, fir=None):
        samples = _pcm(samples)
        if fir is not None:
            from scipy import signal
            taps = np.asarray(fir, np.float64)
            if taps.ndim != 1 or not len(taps) or not np.isfinite(taps).all():
                raise ValueError("finite nonempty FIR taps required")
            if self.fir is None or not np.array_equal(taps, self.fir):
                self.fir, self.delay = taps.copy(), np.zeros(len(taps)-1)
            samples, self.delay = signal.lfilter(taps, [1.], samples, zi=self.delay)
        else:
            self.reset()
        codes = np.clip(np.rint(samples*128+128), 0, 255).astype(np.uint8)
        return self._block("audio", codes, sample_rate)

    def scan(self, amplitudes, source_rate=SAMPLE_RATE, fft_size=FFT_SIZE, *, output_rate=16000):
        amplitudes = np.asarray(amplitudes, dtype=np.float64)
        if amplitudes.shape != (fft_size//2+1,) or not np.isfinite(amplitudes).all() or np.any(amplitudes < 0):
            raise ValueError("expected a finite one-sided amplitude spectrum")
        self.reset()
        decibels = 20*np.log10(np.maximum(amplitudes, 1e-5))
        codes = np.rint(np.clip((decibels+100)/100, 0, 1)*255).astype(np.uint8)
        return self._block("spectrum", codes, output_rate, source_rate/fft_size)

    @staticmethod
    def _block(mode, codes, rate, frequency_step=0.):
        if type(rate) is not int or rate <= 0:
            raise ValueError("invalid DAC output rate")
        codes = codes.copy()
        sync = np.zeros(len(codes), dtype=np.uint8)
        if mode == "spectrum":
            sync[0] = 1
        codes.flags.writeable = sync.flags.writeable = False
        return DacBlock(mode, codes, sync, rate, frequency_step)

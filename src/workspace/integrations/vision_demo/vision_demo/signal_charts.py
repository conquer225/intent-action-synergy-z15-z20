"""Display arithmetic only; original inference features remain immutable."""
import numpy as np


def spectrum_columns(frequencies, dbfs, count=64):
    """Log-frequency display columns containing actual bin maxima, never sums.

    Empty bands remain NaN. The final band includes 20 kHz; out-of-range
    frequencies are excluded. This transform does not alter FFT/model results.
    """
    f=np.asarray(frequencies,dtype=float);db=np.asarray(dbfs,dtype=float)
    if (f.ndim!=1 or db.shape!=f.shape or not len(f) or
            not np.isfinite(f).all() or not np.isfinite(db).all() or
            type(count) is not int or not 1<=count<=256):
        raise ValueError('Finite frequency/dBFS pairs and bounded columns required')
    edges=np.geomspace(20.,20000.,count+1)
    keep=(f>=20.)&(f<=20000.)
    # Classify in log space: geomspace's rounded 200/2000 edges must not
    # move an exact decade boundary into the previous display column.
    indices=np.minimum(np.floor(np.log10(f[keep]/20.)*count/3.).astype(int),count-1)
    peaks=np.full(count,-np.inf)
    np.maximum.at(peaks,indices,db[keep]);peaks[~np.isfinite(peaks)]=np.nan
    return dict(edges_hz=edges,peak_dbfs=peaks)


def wave_scale(samples):
    """One shared, rounded microvolt scale across all eight channels."""
    a = np.asarray(samples, dtype=float)
    if a.size == 0 or not np.isfinite(a).all():
        return 5.
    limit = max(5., float(np.percentile(np.abs(a), 99)))
    return float(5 * np.ceil(limit / 5))


def covariance_maps(values):
    """Undo sqrt(2)-weighted upper-triangle vectorization, no new estimate."""
    if values is None:
        return None
    a = np.asarray(values, dtype=float)
    if a.shape != (105,) or not np.isfinite(a).all():
        return None
    upper = np.triu_indices(6)
    rows = a.reshape(5, 21).copy()
    rows[:, upper[0] != upper[1]] /= np.sqrt(2)
    maps = np.zeros((5, 6, 6))
    maps[:, upper[0], upper[1]] = rows
    maps[:, upper[1], upper[0]] = rows
    return maps


def spectrogram(samples, rate):
    """Actual display-signal mean channel power; only up to its Nyquist limit.

    64-sample Hann windows, four-sample hops; dB relative to 1 microvolt^2/Hz.
    Window centres are relative to the start of the supplied packet.
    """
    a = np.asarray(samples, dtype=float)
    if (a.ndim != 2 or a.shape[1] != 8 or len(a) < 64
            or not np.isfinite(a).all() or rate <= 0):
        return None
    starts = np.arange(0, len(a) - 63, 4)
    window = np.hanning(64)
    sections = np.stack([a[start:start+64] for start in starts])
    sections = sections - np.mean(sections, axis=1, keepdims=True)
    fft = np.fft.rfft(sections * window[None, :, None], axis=1)
    power = np.mean(np.abs(fft)**2, axis=2) / (rate * np.sum(window**2))
    power[:, 1:-1] *= 2
    return dict(frequency_hz=np.fft.rfftfreq(64, 1./rate),
                time_seconds=(starts + 32) / float(rate),
                power_db=10*np.log10(np.maximum(power.T, 1e-12)))


def pcm_wave_scale(stereo):
    """Shared 1/2/5 amplitude scale in PCM full-scale units, never channel gain."""
    a=np.asarray(stereo,dtype=float)
    peak=max(.01,float(np.max(np.abs(a)))) if a.size and np.isfinite(a).all() else .01
    decade=10.**np.floor(np.log10(peak))
    return float(next(v*decade for v in (1,2,5,10) if v*decade>=peak-1e-12))

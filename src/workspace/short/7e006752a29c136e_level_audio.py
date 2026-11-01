"""Offline fixed-gain PCM leveling. Original files and playback volume are unchanged."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import wave

import numpy as np


def measure(path):
    count, energy, peak = 0, 0., 0
    with wave.open(str(path), 'rb') as wav:
        if (wav.getframerate(),wav.getnchannels(),wav.getsampwidth(),wav.getcomptype()) != (48000,2,2,'NONE'):
            raise ValueError('Expected prepared 48 kHz PCM16 stereo WAV')
        if not 0 < wav.getnframes() <= 600*48000:
            raise ValueError('Expected nonempty audio, at most ten minutes')
        frames = wav.getnframes()
        while True:
            data = wav.readframes(48000)
            if not data:
                break
            samples = np.frombuffer(data,dtype='<i2').astype(np.float64)
            count += len(samples)
            energy += float(np.dot(samples,samples))
            peak = max(peak,int(np.max(np.abs(samples))))
    if count != frames*2:
        raise ValueError('Truncated PCM file')
    rms = math.sqrt(energy/count)
    return dict(frames=frames,peak=peak,rms=rms,
                peak_dbfs=20*math.log10(peak/32768) if peak else None,
                rms_dbfs=20*math.log10(rms/32768) if rms else None)


def level(source, target):
    source, target = Path(source), Path(target)
    before_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    before = measure(source)
    if not before['peak']:
        raise ValueError('Silent audio cannot be made audible with fixed gain')
    # Match the existing music's approximate RMS, without compression or clipping.
    desired_rms = 32768*10**(-23/20)
    peak_limit = math.floor(32767*10**(-3/20))
    gain = min(desired_rms/before['rms'],peak_limit/before['peak'],10**(30/20))
    created = False
    try:
        with target.open('xb') as output:
            created = True
            with wave.open(str(source),'rb') as src, wave.open(output,'wb') as dst:
                dst.setnchannels(2); dst.setsampwidth(2); dst.setframerate(48000)
                while True:
                    data = src.readframes(48000)
                    if not data:
                        break
                    values = np.rint(np.frombuffer(data,dtype='<i2').astype(np.float64)*gain)
                    if np.max(np.abs(values)) > peak_limit:
                        raise ValueError('Peak ceiling exceeded before integer conversion')
                    dst.writeframesraw(values.astype('<i2').tobytes())
        after = measure(target)
        if after['frames'] != before['frames'] or hashlib.sha256(source.read_bytes()).hexdigest() != before_hash:
            raise ValueError('Source changed or sample count differs')
    except Exception:
        if created:
            target.unlink()
        raise
    return dict(source=str(source),target=str(target),before=before,after=after,
                gain_db=20*math.log10(gain),source_sha256=before_hash,
                target_sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
                hardware_opened=False,perceived_loudness_verified=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source',type=Path)
    parser.add_argument('new_output',type=Path)
    args = parser.parse_args()
    print(json.dumps(level(args.source,args.new_output)))

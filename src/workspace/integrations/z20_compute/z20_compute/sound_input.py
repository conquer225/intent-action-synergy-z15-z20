"""Bounded PC microphone/file adapter into the existing 40-feature sound model."""
import io,uuid,wave
import numpy as np
from .audio import sound_features,resample_audio


def decode_sound_wav(data):
    if not isinstance(data,bytes) or not 44<=len(data)<=2*1024*1024:raise ValueError('请提供不超过 2 MB 的 PCM WAV')
    try:
        with wave.open(io.BytesIO(data),'rb') as source:
            channels,rate,width=source.getnchannels(),source.getframerate(),source.getsampwidth()
            frames=source.getnframes()
            if channels not in (1,2) or width!=2 or not 8000<=rate<=96000 or not 1<=frames<=rate*10:
                raise ValueError('需要十秒以内、16位单声道或双声道 PCM WAV')
            raw=source.readframes(frames)
            if len(raw)!=frames*channels*2:raise ValueError('WAV 数据不完整')
    except (wave.Error,EOFError) as exc:raise ValueError('无法读取 PCM WAV') from exc
    samples=np.frombuffer(raw,dtype='<i2').reshape(-1,channels).mean(axis=1)/32768.
    if rate!=16000:samples=resample_audio(samples,rate)
    if len(samples)<16000:samples=np.pad(samples,(0,16000-len(samples)))
    # Select the highest-energy one-second interval, on a 100 ms grid.
    offsets=list(range(0,len(samples)-16000+1,1600))
    start=max(offsets,key=lambda n:float(np.sum(samples[n:n+16000]**2)))
    return samples[start:start+16000]


def prepare_sound_input(samples,*,source):
    if source not in ('live:pc_microphone','recorded:pc_wav'):raise ValueError('unknown sound source')
    try:vector=sound_features(samples).tolist();valid=True
    except ValueError:vector=None;valid=False
    return dict(vector=vector,valid=valid,source=source,window_id='pc-sound:'+uuid.uuid4().hex)

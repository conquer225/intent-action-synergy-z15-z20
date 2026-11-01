"""A real chronological FFT window over an explicitly looping recorded PCM clip."""
import math
import numpy as np


class SequentialSpectrum:
    def __init__(self, pcm, *, source, started):
        self.pcm=np.asarray(pcm,dtype=np.float64)
        if self.pcm.shape!=(16000,) or not np.isfinite(self.pcm).all():
            raise ValueError('one second of 16kHz mono recorded PCM required')
        self.source,self.started=source,started
        self.hann=np.hanning(1024)
        self.frequency=np.fft.rfftfreq(1024,1./16000)
        self.edges=np.geomspace(20,8000,65)

    def at(self,now):
        if not math.isfinite(now) or now<self.started:raise ValueError('invalid recording clock')
        sequence=int(math.floor((now-self.started)*20+1e-8))
        offset=(sequence*800)%16000
        window=self.pcm[(np.arange(1024)+offset)%16000]
        amplitude=np.abs(np.fft.rfft(window*self.hann))*2/self.hann.sum()
        db=20*np.log10(np.maximum(amplitude,1e-8))
        bands=[]
        for low,high in zip(self.edges[:-1],self.edges[1:]):
            selected=db[(self.frequency>=low)&(self.frequency<high)]
            bands.append(int(np.clip(round(((float(selected.max()) if len(selected) else -80)+80)*255/80),0,255)))
        rms=float(np.sqrt(np.mean(window*window)))
        return dict(source=self.source,window_sequence=sequence,sample_offset=offset,
            position_seconds=offset/16000.,sample_rate_hz=16000,fft_size=1024,
            band_values=bands,frequency_edges_hz=self.edges.round(2).tolist(),
            db_min=-80,db_max=0,band_reduction='maximum_of_actual_fft_bins',
            peak_frequency_hz=float(self.frequency[np.argmax(amplitude)]) if rms>=1e-4 else None,
            recording_loop=True,playback_started=False)

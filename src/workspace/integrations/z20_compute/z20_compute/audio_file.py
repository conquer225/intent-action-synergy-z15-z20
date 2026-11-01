"""One-second PCM file analysis. This module contains no playback or DAC path."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import numpy as np
from .audio import sound_features, spectrum


def read_pcm(path):
    path=Path(path)
    if path.stat().st_size>1024*1024:raise ValueError('oversized audio sample')
    data=path.read_bytes()
    if (len(data)<12 or data[:4]!=b'RIFF' or data[8:12]!=b'WAVE'
            or struct.unpack_from('<I',data,4)[0]+8!=len(data)):
        raise ValueError('invalid or truncated RIFF/WAVE container')
    offset,format_info,payload=12,None,None
    while offset+8<=len(data):
        tag,size=struct.unpack_from('<4sI',data,offset);offset+=8
        if offset+size>len(data):raise ValueError('truncated WAV chunk')
        if tag==b'fmt ':
            if format_info is not None or size<16:raise ValueError('invalid WAV format chunk')
            format_info=struct.unpack_from('<HHIIHH',data,offset)
        elif tag==b'data':
            if payload is not None:raise ValueError('duplicate PCM data chunk')
            payload=data[offset:offset+size]
        offset+=size+(size%2)
    if offset!=len(data) or format_info!=(1,1,16000,32000,2,16) or payload is None or len(payload)!=32000:
        raise ValueError('expected one-second 16kHz mono PCM16 WAV')
    return np.frombuffer(payload,'<i2').astype(np.float64)/32768.


def signal_analysis(samples):
    rms=float(np.sqrt(np.mean(samples*samples)))
    # Averaging full 1024-point window spectra avoids selecting an unrepresentative
    # final frame while retaining the specified FFT frequency resolution.
    spectra=[spectrum(samples[i:i+1024]) for i in range(0,16000-1024+1,512)]
    frequencies=spectra[0][0];amplitudes=np.mean([s[1] for s in spectra],axis=0)
    blocks=samples.reshape(160,100)
    return dict(rms=rms,dbfs=float(20*np.log10(max(rms,1e-8))),
            waveform_minmax=np.column_stack((blocks.min(1),blocks.max(1))).tolist(),
            fft_size=1024,sample_rate_hz=16000,frequency_hz=frequencies.tolist(),
            amplitudes=amplitudes.tolist(),peak_frequency_hz=float(frequencies[np.argmax(amplitudes)]) if rms>=1e-4 else None)


def analyze_file(path,model,*,backend=None):
    samples=read_pcm(path)
    result=dict(valid=False,class_id=None,scores=None,state='silence',
        model_version=getattr(model,'version','unavailable'),backend='not_run',
        source_file=Path(path).name,source_sha256=hashlib.sha256(Path(path).read_bytes()).hexdigest(),
        playback_started=False,
        analysis=signal_analysis(samples))
    try: features=sound_features(samples)
    except ValueError as exc:
        result['state']=str(exc);return result
    prediction=model.predict(features,backend=backend)
    result.update(valid=prediction.valid,class_id=prediction.class_id,
                  scores=prediction.scores.tolist() if prediction.valid else None,
                  state=prediction.state,model_version=prediction.model_version,backend=prediction.backend)
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--file',type=Path,required=True)
    parser.add_argument('--model',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--backend',choices=('ps','pl'),default='ps')
    args=parser.parse_args()
    from .training import ModelBundle
    resources=()
    if args.backend=='pl':
        from .headless_server import open_npu
        resources=open_npu()
    try:
        result=analyze_file(args.file,ModelBundle.load(args.model),backend=resources[0] if resources else None)
        args.output.write_text(json.dumps(result,indent=2),encoding='utf-8')
        print(json.dumps(dict(state=result['state'],class_id=result['class_id'],backend=result['backend'])))
    finally:
        if resources:
            for resource in resources:resource.close()


if __name__=='__main__':main()

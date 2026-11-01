"""Real ARM file/feature/NPU checks; recognition metrics remain separate."""
import argparse
import hashlib
import json
from pathlib import Path
import time
import struct
import numpy as np
from .audio import sound_features
from .audio_file import analyze_file,read_pcm
from .headless_server import open_npu
from .training import Dataset,ModelBundle,classification_metrics


class CheckedBackend:
    def __init__(self,hardware):
        self.hardware,self.name,self.calls=hardware,hardware.name,0
    def infer(self,model,values):
        reference=model.infer(values)
        actual=self.hardware.infer(model,values)
        if not np.array_equal(reference,actual):raise ValueError('PL/PS integer mismatch')
        self.calls+=1
        return actual


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,required=True)
    parser.add_argument('--model',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    manifest=json.loads((args.root/'manifest.json').read_text(encoding='utf-8'))
    dataset=Dataset.load(args.root/'features.npz')
    model=ModelBundle.load(args.model)
    if len(manifest['windows'])!=len(dataset.x):raise ValueError('feature/window manifest length mismatch')
    hardware,pool,registers=open_npu();checked=CheckedBackend(hardware)
    report=dict(passed=False,board_executed=True,backend=hardware.name,model_version=model.version,
                scope='registered recorded files; source-group labels; model quality reported separately',
                cases=[],examples={},max_feature_absolute_error=0.)
    started=time.monotonic()
    try:
        for index,row in enumerate(manifest['windows']):
            path=args.root/row['file']
            if hashlib.sha256(path.read_bytes()).hexdigest()!=row['pcm_sha256']:
                raise ValueError('PCM hash mismatch')
            features=sound_features(read_pcm(path))
            error=float(np.max(np.abs(features-dataset.x[index])))
            report['max_feature_absolute_error']=max(report['max_feature_absolute_error'],error)
            if not np.allclose(features,dataset.x[index],rtol=1e-6,atol=1e-5):
                raise ValueError('PC/ARM feature mismatch')
            output=analyze_file(path,model,backend=checked)
            report['cases'].append(dict(file=row['file'],split=row['split'],group=row['group'],
                expected_class=row['class_id'],class_id=output['class_id'],scores=output['scores'],
                valid=output['valid'],integer_reference_equal=True,
                source_sha256=output['source_sha256'],timing=hardware.last_timing.copy()))
            label=str(row['class_id'])
            if label not in report['examples']:report['examples'][label]=output
        silence=args.root/'silence-diagnostic.wav'
        silence.write_bytes(struct.pack('<4sI4s4sIHHIIHH4sI',b'RIFF',32036,b'WAVE',b'fmt ',
                                       16,1,1,16000,32000,2,16,b'data',32000)+bytes(32000))
        before=checked.calls
        output=analyze_file(silence,model,backend=checked)
        if output['valid'] or output['class_id'] is not None or checked.calls!=before:
            raise ValueError('silence reached NPU or retained classification')
        report['silence_rejected']=True
        report['metrics']={}
        for split in ('train','validation','test'):
            rows=[row for row in report['cases'] if row['split']==split]
            report['metrics'][split]=classification_metrics([row['expected_class'] for row in rows],
                                                            [row['class_id'] for row in rows])
        report.update(passed=True,hardware_calls=checked.calls,elapsed_seconds=time.monotonic()-started)
    except BaseException as exc:
        report['error']=type(exc).__name__+': '+str(exc)
        raise
    finally:
        args.output.write_text(json.dumps(report,indent=2),encoding='utf-8')
        hardware.close();pool.close();registers.close()
        print(json.dumps(dict(passed=report['passed'],hardware_calls=checked.calls)),flush=True)


if __name__=='__main__':main()

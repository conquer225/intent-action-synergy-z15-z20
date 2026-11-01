"""Private synthetic load diagnosis; no serial, PL, production outputs or saves."""
import argparse
import json
from pathlib import Path
import time

import numpy as np

from calibration_session import CalibrationSession
from cyton_covariance import CovarianceFeatureStream, CovarianceSVM
from cyton_fatigue import FourChannelFatigue
from cyton_sqi import CausalEEGFilter, CytonSQIMonitor, primary_windows, segmented_sqi
from primary_window import PrimaryWindowProcessor
from replay_stage_trace import StageTrace


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--models',type=Path,required=True)
    parser.add_argument('--checkpoint',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.resolve().parent.name.startswith('gl-calibration-install-') is False:
        raise ValueError('Diagnosis output must stay in its private stage')
    saved=json.loads(args.checkpoint.read_text())
    channels=tuple(saved['context']['channels'])
    fatigue=FourChannelFatigue(args.models/'cyton_fatigue_overlap4.json')
    sqi=CytonSQIMonitor(calibration_windows=15)
    checkpoint=CalibrationSession(args.checkpoint,saved['context'])
    if not checkpoint.load(sqi,fatigue):raise ValueError('Baseline could not be read')
    processor=PrimaryWindowProcessor(sqi,fatigue,
        CovarianceSVM(args.models/'gameemo_covariance_svm.npz'),
        CovarianceFeatureStream(channels,storage='array'),None,None,None,channels,
        saved['context']['microvolts_per_count'],'arm',primary_windows,segmented_sqi)
    trace=StageTrace(slow_seconds=.05,max_slow_events=100,thread_resources=True)
    for owner,name,label in ((processor,'evaluate','window_inclusive'),
            (processor,'snapshot','window_snapshot'),(processor,'descriptors','raw_quality'),
            (sqi,'process','filtered_quality'),(processor.covariance_stream,'append','emotion_filter'),
            (processor.covariance_stream,'feature','emotion_features'),
            (processor.covariance_model,'predict','emotion_predict'),
            (processor.covariance_model,'predict_feature','emotion_kernel_diagnostic'),
            (fatigue,'append','fatigue_filter'),(fatigue,'process_window','fatigue_predict')):
        trace.wrap(owner,name,label)
    rng=np.random.default_rng(20261011)
    t=np.arange(8000)/250
    signal=np.stack([18*np.sin(2*np.pi*(8+i)*t) for i in range(8)],axis=1)
    signal+=rng.normal(0,2,signal.shape)
    counts=np.rint(signal/processor.scale)
    filtered=CausalEEGFilter().process(counts*processor.scale)
    counters=dict(packets_seen=0,dropped_packets=0,sequence_gaps=0,
                  unresolved_gaps=0,malformed_bytes=0)
    began=time.monotonic();cpu=time.thread_time();windows=0
    for i,(raw,clean) in enumerate(zip(counts,filtered)):
        counters['packets_seen']=i+1;trace.packet_index=i
        if processor.append(raw,clean,False,counters) is not None:windows+=1
    # Time the kernel even if this synthetic signal fails the saved SQI gate.
    # These values are never published as accepted emotion predictions.
    for _ in range(8):
        processor.covariance_model.predict_feature(processor.covariance_stream.feature())
    trace.save(args.output)
    result=json.loads(args.output.read_text())
    result.update(samples=len(counts),windows=windows,wall_seconds=time.monotonic()-began,
        thread_cpu_seconds=time.thread_time()-cpu,calibration_windows=processor.calibration_progress,
        scope='Synthetic window load with a read-only baseline; not live timing or recognition accuracy')
    args.output.write_text(json.dumps(result,indent=2));args.output.chmod(0o600)
    print(json.dumps({k:result[k] for k in ('samples','windows','wall_seconds','thread_cpu_seconds','calibration_windows')}))


if __name__=='__main__':main()

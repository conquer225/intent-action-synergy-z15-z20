"""Accelerated recorded replay into a separate, explicitly offline status endpoint."""
import argparse
import json
import time
from collections import Counter
from pathlib import Path
import numpy as np
from seed_shadow import SeedShadow
from seed_quality_runtime import CHANNELS


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--input',required=True)
    p.add_argument('--weights',required=True)
    p.add_argument('--output',required=True)
    args=p.parse_args()
    data=np.loadtxt(args.input,delimiter=',',skiprows=5,usecols=range(9))
    shadow=SeedShadow(args.weights,CHANNELS,source='replay')
    events=[]; times=[]
    for i,row in enumerate(data):
        start=time.perf_counter()
        # Source-time clock, not accelerated wall time, is used for link timing.
        emitted=shadow.packet(row[1:9],int(row[0]),now=i/250)
        times.append(time.perf_counter()-start)
        events.extend(emitted)
    counts=dict(Counter(e['state'] for e in events))
    result={'source':'replay','finished':True,'valid':False,'state':'replay_finished',
        'samples':len(data),'input_seconds':len(data)/250,'sequence_gaps':shadow.gaps,
        'compute_seconds':float(sum(times)),'counts':counts,
        'prediction_window_fraction':counts.get('prediction',0)*12/(len(data)/250),
        'packet_ms_p95':float(np.quantile(times,.95)*1000),
        'packet_ms_max':float(max(times)*1000),
        'scope':'ARM gate/filter/features/adaptation plus status writes; accelerated replay, no serial/network latency or accuracy'}
    Path(args.output).write_text(json.dumps(result,indent=2),encoding='utf-8')
    shadow.publish({**result,'summary':{'拒绝片段':counts.get('rejected',0),'预测窗口':counts.get('prediction',0),'计算秒':round(sum(times),3)}})
    print(json.dumps(result))


if __name__=='__main__':
    main()

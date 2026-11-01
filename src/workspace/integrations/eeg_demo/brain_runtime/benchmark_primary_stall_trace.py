"""Numeric/CPU overhead check for private probes; no USB, PL or release writes."""
import json
import time

import numpy as np
from cyton_sqi import CausalEEGFilter
from replay_stage_trace import StageTrace


def main():
    samples=np.random.RandomState(18).normal(size=(6000,8))*20
    original=CausalEEGFilter.process
    pairs=[]
    for _ in range(3):
        rows=[]
        outputs=[]
        for instrumented in (False,True):
            trace=StageTrace(slow_seconds=.050,max_slow_events=256,thread_resources=True)
            CausalEEGFilter.process=original
            if instrumented:
                trace.wrap(CausalEEGFilter,'process','primary_filter')
            try:
                stream=CausalEEGFilter()
                wall=time.monotonic();cpu=time.thread_time()
                result=np.concatenate([stream.process(samples[i:i+10]) for i in range(0,len(samples),10)])
                rows.append(dict(instrumented=instrumented,thread_cpu_s=time.thread_time()-cpu,
                                 wall_s=time.monotonic()-wall,calls=600))
                outputs.append(result)
            finally:
                CausalEEGFilter.process=original
        np.testing.assert_array_equal(outputs[0],outputs[1])
        pairs.append(rows)
    reference=sum(rows[0]['thread_cpu_s'] for rows in pairs)
    measured=sum(rows[1]['thread_cpu_s'] for rows in pairs)
    print(json.dumps(dict(pairs=pairs,numeric_outputs_identical=True,
        measured_thread_cpu_overhead_percent=(measured/reference-1)*100,
        scope='Three short filter-only pairs with active display; not full-pipeline overhead or real-time qualification')))


if __name__=='__main__':main()

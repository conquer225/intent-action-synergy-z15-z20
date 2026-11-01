"""Derive compact engineering evidence from saved traces, without changing a model."""
import json
from pathlib import Path
import numpy as np

OUT=Path(__file__).resolve().parent/'output/stall_trace_20260927'


def main():
    result={}
    for name in ('baseline','cached','without_telemetry','primary_tmpfs'):
        directory=OUT/name
        report=json.loads((directory/'report.json').read_text())
        stages=json.loads((directory/'stages.json').read_text())
        slow=json.loads((directory/'slow_packets.json').read_text())
        worst=max(slow,key=lambda row:row['wall_ms'])
        result[name]=dict(total_cpu_s=report['parent_cpu_seconds']+report['children_cpu_seconds'],
            packet_age_p95_ms=report['packet_input_age_p95_ms'],
            packet_age_max_ms=report['packet_input_age_max_ms'],
            packet_compute_p99_ms=report['packet_compute_p99_ms'],
            worst_packet=worst,
            worst_packet_non_cpu_fraction=1-worst['thread_cpu_ms']/worst['wall_ms'],
            stages=stages['stages'])
    passive=json.loads((OUT/'passive.json').read_text())['rows']
    fresh=[row for row in passive if row.get('age_s',float('inf'))<3 and row.get('runtime')]
    ages=[row['runtime']['input_age_at_snapshot_ms'] for row in fresh]
    counters=[row['packets_seen'] for row in fresh]
    first=np.array([int(x) for x in passive[0]['system_cpu'].split()[1:9]])
    last=np.array([int(x) for x in passive[-1]['system_cpu'].split()[1:9]])
    delta=last-first
    result['passive']=dict(samples=len(passive),fresh_samples=len(fresh),
        observed_packet_progress=counters[-1]-counters[0] if counters else None,
        snapshot_age_p95_ms=float(np.quantile(ages,.95)) if ages else None,
        snapshot_age_max_ms=max(ages) if ages else None,
        system_busy_fraction=float(1-(delta[3]+delta[4])/delta.sum()),
        system_iowait_fraction=float(delta[4]/delta.sum()),
        scope='System fractions average across both cores; packet counter resets invalidate simple progress.')
    (OUT/'summary.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    for name,value in result.items():
        print(name,json.dumps({k:v for k,v in value.items() if k!='stages'},indent=2))


if __name__=='__main__':
    main()

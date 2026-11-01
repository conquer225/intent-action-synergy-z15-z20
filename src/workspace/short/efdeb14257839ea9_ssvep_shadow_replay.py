"""Replay old Cyton counts/sequence through the packet bridge, never live status."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import resource
import time

import numpy as np

from ssvep_shadow import SSVEPShadow, CHANNELS


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    here = Path(__file__).resolve().parent
    shadow = SSVEPShadow(here/'ssvep_causal_protocol.json', here/'ssvep_candidate_sos.npy',
                        CHANNELS, source='replay', status_path=args.output/'status.json')
    rows = np.loadtxt(args.input, delimiter=',', skiprows=5, usecols=range(9))
    events, timings = [], []
    began, cpu = time.perf_counter(), time.process_time()
    for i, row in enumerate(rows):
        start = time.perf_counter()
        events.extend(shadow.packet(row[1:9], int(row[0]), now=i/250,
                                   adc_rails=np.abs(row[7:9]) >= 187500*.99))
        timings.append(time.perf_counter()-start)
    wall, cpu = time.perf_counter()-began, time.process_time()-cpu
    counts = dict(Counter(e['state'] for e in events))
    reasons = Counter()
    for event in events:
        for channel in event.get('quality', {}).get('channels', []):
            reasons.update(channel['hard_reasons'])
    report = dict(source='replay', finished=True, valid=False, control_enabled=False,
                  samples=len(rows), input_seconds=len(rows)/250, events=len(events),
                  states=counts, hard_reasons=dict(reasons), sequence_gaps=shadow.gaps,
                  wall_seconds=wall, cpu_seconds=cpu,
                  packet_ms_p95=float(np.quantile(timings,.95)*1000),
                  packet_ms_max=float(max(timings)*1000),
                  rss_peak_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                  input_sha256=hashlib.sha256(args.input.read_bytes()).hexdigest(),
                  scope='Unlabelled historical recording, user-declared cap; no SSVEP accuracy claim. Accelerated replay, not UART timing.')
    (args.output/'events.json').write_text(json.dumps(events, ensure_ascii=False, allow_nan=False), encoding='utf-8')
    (args.output/'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    shadow.disconnect('replay_finished')
    shadow.publish('replay_finished', finished=True, summary={'记录秒数':report['input_seconds'],
                   '候选窗口':counts.get('candidate_only',0),'拒绝窗口':counts.get('signal_invalid',0),
                   '计算秒数':round(wall,3)})
    print(json.dumps(report, indent=2), flush=True)


if __name__ == '__main__':
    main()

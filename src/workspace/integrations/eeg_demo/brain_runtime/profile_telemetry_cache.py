"""Compare the unchanged API payload against byte reuse, using isolated replay data."""
import argparse
import json
from pathlib import Path
import tempfile
import time
import numpy as np
from guardianloop_web import read_payload, TelemetryResponseCache


def main():
    p=argparse.ArgumentParser();p.add_argument('--input',required=True);p.add_argument('--output',required=True)
    a=p.parse_args();payload=json.loads(Path(a.input).read_text())
    payload.update(source='offline_replay_not_live',real=False)
    reports={}
    with tempfile.TemporaryDirectory(prefix='telemetry-cache-') as folder:
        path=Path(folder)/'telemetry.json';path.write_text(json.dumps(payload,separators=(',',':')))
        cache=TelemetryResponseCache(path)
        for name in ('previous_json_decode_encode','candidate_cached_bytes'):
            timings=[]
            for i in range(41):
                start=time.perf_counter()
                if name.startswith('previous'):
                    t,stale=read_payload(path,3)
                    body=json.dumps({'telemetry':t,'stale':stale},ensure_ascii=False,allow_nan=False).encode()
                else:body=cache.body()
                elapsed=time.perf_counter()-start
                assert json.loads(body)['telemetry']==payload
                if i:timings.append(elapsed)
            reports[name]={'calls':40,'median_ms':float(np.median(timings)*1000),
                           'p95_ms':float(np.quantile(timings,.95)*1000),'bytes':len(body)}
        changed=[]
        for i in range(40):
            payload['sample_index']+=1
            temp=path.with_suffix('.tmp');temp.write_text(json.dumps(payload,separators=(',',':')));temp.replace(path)
            start=time.perf_counter();body=cache.body();changed.append(time.perf_counter()-start)
            assert json.loads(body)['telemetry']==payload
        reports['candidate_changed_file']={'calls':40,'median_ms':float(np.median(changed)*1000),
                                           'p95_ms':float(np.quantile(changed,.95)*1000)}
    Path(a.output).write_text(json.dumps({'scope':'API response construction only, excludes HTTP transfer/client rendering',
                                       'runs':reports},indent=2))
    print(json.dumps(reports))


if __name__=='__main__':main()

"""PC now, Z15 later: replay actual tapped features using the shared client."""
import argparse
import json
from pathlib import Path
import socket
import time
from .service import FeaturePublisher
from .training import PREPROCESSORS


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', required=True)
    parser.add_argument('--port', type=int, default=9020)
    parser.add_argument('--features', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    data = json.loads(args.features.read_text(encoding='utf-8'))
    report = dict(source=data['source'], transport='real TCP', results=[])
    client = FeaturePublisher(socket.create_connection((args.host, args.port), timeout=5))
    client.start()
    try:
        for index, record in enumerate(data['records']):
            task, window = record['task'], 'lemon:%d:%d' % (record['end_sample'], index)
            baseline=record['baseline']
            reference=(dict(kind='SEED_linear',class_id=int(baseline['class_id'])+1,scores=baseline['scores'])
                       if task=='emotion' else dict(kind='HGB_regressor',class_id=int(baseline['level']),value=baseline['perclos']))
            client.offer_features(task, record['features'], feature_version=PREPROCESSORS[task],
                window_id=window, source='recorded:LEMON', quality=1.,original_reference=reference)
            deadline = time.monotonic()+5
            while time.monotonic() < deadline:
                result = client.results.get(task)
                if result is not None and result.body['window_id'] == window: break
                time.sleep(.01)
            else: raise TimeoutError('no result for '+window)
            report['results'].append(dict(result=result.body, original_reference=record['baseline']))
    finally:
        client.close()
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(dict(results=len(report['results']), output=str(args.output))))


if __name__ == '__main__': main()

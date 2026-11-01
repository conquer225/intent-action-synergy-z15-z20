"""Real wired NPU/camera soak, with bounded reports and fresh status samples."""
import argparse
from collections import deque
import json
from pathlib import Path
import socket
import time
import urllib.request
from z20_compute.service import FeaturePublisher
from z20_compute.training import PREPROCESSORS


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', required=True)
    parser.add_argument('--seconds', type=float, default=1800)
    parser.add_argument('--features', type=Path, default=Path('artifacts/headless/lemon_features.json'))
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.seconds <= 0: parser.error('positive duration required')
    rows = json.loads(args.features.read_text(encoding='utf-8'))['records']
    report = dict(scope='wired feature inference with actual camera preview', requested_seconds=args.seconds,
                  passed=False, running=True, windows=0, reconnects=0, samples=[], errors=[])
    durations, started, last_saved = deque(maxlen=100), time.monotonic(), 0.
    client = None
    def connect():
        item = FeaturePublisher(socket.create_connection((args.host, 9020), timeout=5)); item.start(); return item
    def status():
        return json.load(urllib.request.urlopen('http://'+args.host+':9021/status.json', timeout=5))
    def save():
        report['elapsed_seconds'] = time.monotonic()-started
        report['recent_round_trip_seconds'] = list(durations)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        temporary = args.output.with_suffix('.tmp')
        temporary.write_text(json.dumps(report, indent=2), encoding='utf-8'); temporary.replace(args.output)
    try:
        client = connect()
        while time.monotonic()-started < args.seconds:
            index = report['windows']; row = rows[index % len(rows)]; task=row['task']; window='soak:%d'%index
            then = time.monotonic()
            client.offer_features(task, row['features'], feature_version=PREPROCESSORS[task],
                                  window_id=window, source='recorded:LEMON:soak')
            deadline = time.monotonic()+5
            while time.monotonic() < deadline:
                result = client.results.get(task)
                if result is not None and result.body['window_id'] == window: break
                time.sleep(.01)
            else: raise TimeoutError('missing fresh NPU result')
            if not result.body.get('integer_reference_equal') or result.body['backend'] != 'PL_z20_mlp':
                raise AssertionError('actual PL/reference agreement required')
            durations.append(time.monotonic()-then); report['windows'] += 1
            if time.monotonic()-last_saved >= 60:
                current = status()
                if not current['preview_available'] or current['counters']['errors']:
                    raise AssertionError('camera preview unavailable or inference errors')
                report['samples'].append(current)
                report['samples'] = report['samples'][-60:]
                save(); print(json.dumps(dict(windows=report['windows'], elapsed=report['elapsed_seconds'])), flush=True)
                last_saved=time.monotonic()
            if report['windows'] % 300 == 0:
                client.close(); time.sleep(.3)
                if any(v['valid'] for v in status()['results'].values()):
                    raise AssertionError('disconnect retained classification')
                client=connect(); report['reconnects'] += 1
            time.sleep(max(0., 1-(time.monotonic()-then)))
        report['passed'] = True
    except BaseException as exc:
        report['errors'].append(type(exc).__name__+': '+str(exc))
        raise
    finally:
        if client is not None: client.close()
        report['running'] = False
        save()


if __name__ == '__main__': main()

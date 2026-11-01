"""Read existing runtime diagnostics only; no raw EEG export or device operations."""
import argparse
import json
from pathlib import Path
import time


def observe(destination, seconds):
    rows = []
    start = time.monotonic()
    for index in range(seconds):
        time.sleep(max(0., start+index-time.monotonic()))
        row = dict(elapsed_s=time.monotonic()-start)
        try:
            telemetry = json.loads(Path('/run/guardianloop/telemetry.json').read_text())
            row.update(packets_seen=telemetry.get('packets_seen'),
                       runtime=telemetry.get('runtime'),
                       age_s=max(0.,time.time()-telemetry['updated_at']),
                       source=telemetry.get('source'))
        except (FileNotFoundError, json.JSONDecodeError, KeyError) as exc:
            row['read_error'] = str(exc)
        row['system_cpu'] = Path('/proc/stat').read_text().splitlines()[0]
        rows.append(row)
    destination.write_text(json.dumps(dict(rows=rows,
        scope='Passive read-only observation, no replay running. No EEG samples exported; '
              'existing quality gates unchanged. This is engineering timing, not accuracy.'),indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--seconds',type=int,default=60)
    arguments = parser.parse_args()
    if arguments.output.exists():
        raise RuntimeError('Output already exists')
    observe(arguments.output,arguments.seconds)

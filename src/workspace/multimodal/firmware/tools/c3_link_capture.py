"""Observe both boards and request only stop/status operations; never enable motion."""
import argparse
import datetime
import json
from pathlib import Path
import re
import threading
import time
import serial
from device_telemetry import hand_telemetry

parser = argparse.ArgumentParser()
parser.add_argument('--seconds', type=int, default=60)
parser.add_argument('--label', default='initial')
parser.add_argument('--observe-only', action='store_true')
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
start = time.monotonic()
results = {}
lock = threading.Lock()

def capture(port, name):
    result = {'lines': 0, 'samples': 0, 'first': None, 'last': None, 'counts': {}, 'exceptions': []}
    try:
        device = serial.Serial()
        device.port = port; device.baudrate = 115200; device.timeout = 0.2
        device.dtr = False; device.rts = False; device.open()
        if name == 's3' and not args.observe_only:
            device.write(b'estop\nhand input contact\npend mode tilt_test\ntilt zero\nstream status\nlink\n')
        with (root / 'records' / f'c3_{args.label}_{name}_20261011.log').open('w', encoding='utf-8') as log:
            buffer = bytearray()
            last_request = 0
            while time.monotonic() - start < args.seconds:
                if name == 's3' and not args.observe_only and time.monotonic() - last_request > 10:
                    device.write(b'link\n'); last_request = time.monotonic()
                buffer.extend(device.read(device.in_waiting or 1))
                while b'\n' in buffer:
                    raw, _, remaining = buffer.partition(b'\n'); buffer = bytearray(remaining)
                    line = raw.decode('utf-8', errors='replace').strip()
                    log.write(f'{time.monotonic()-start:.3f} {line}\n')
                    result['lines'] += 1
                    if name == 's3' and line.startswith('LINK,'):
                        fields = dict(re.findall(r'(\w+):([^,\s]+)', line))
                        result.setdefault('first_link', fields)
                        result['last_link'] = fields
                    if name == 's3' and (line.startswith('strength:') or line.startswith('tilt_deg:')):
                        sensor = dict(re.findall(r'(\w+):([^,\s]+)', line))
                        imu = sensor.get('imu')
                        if imu is not None:
                            counts = result['counts'].setdefault('imu', {})
                            counts[imu] = counts.get(imu, 0) + 1
                    if name == 's3' and line.startswith('TELEM_V3,'):
                        parsed = hand_telemetry(line)
                        enabled = str(int(parsed['output_acknowledged'])) if parsed else 'invalid'
                        counts = result['counts'].setdefault('hand_output_acknowledged', {})
                        counts[enabled] = counts.get(enabled, 0) + 1
                    if line.startswith('BRIDGE,') or line.startswith('# wifi:'):
                        fields = dict(re.findall(r'(\w+):([^,\s]+)', line))
                        result['samples'] += 1
                        if result['first'] is None: result['first'] = fields
                        result['last'] = fields
                        for key, value in fields.items():
                            if key in ('wifi', 'bridge', 'stm_fresh', 'pend_enabled', 'hand_enabled', 'ap', 'session', 'armed', 'stations'):
                                counts = result['counts'].setdefault(key, {})
                                counts[value] = counts.get(value, 0) + 1
                        with lock: results[name] = result
                    if 'Guru Meditation' in line or 'panic' in line.lower(): result['exceptions'].append(line)
                    if 'Both devices OFF' in line: result['manual_boot_banner_seen'] = True
                log.flush()
            device.close()
    except Exception as error:
        result['exceptions'].append(str(error))
    with lock: results[name] = result

threads = [threading.Thread(target=capture, args=(port, name)) for port, name in [('COM20', 'c3'), ('COM27', 's3')]]
for thread in threads: thread.start()
while any(thread.is_alive() for thread in threads):
    for thread in threads: thread.join(timeout=0.1)
    elapsed = time.monotonic() - start
    if int(elapsed) % 60 == 0:
        with lock:
            summary = {name: {'samples': result['samples'], 'last': result['last']} for name, result in results.items()}
        print(json.dumps({'elapsed': round(elapsed), 'boards': summary}), flush=True)
        time.sleep(1)
report = {'duration_seconds': round(time.monotonic() - start, 2), 'boards': results,
          'motion_enabled_by_capture': False, 'timestamp': datetime.datetime.now().isoformat()}
(root / 'records' / f'c3_{args.label}_summary_20261011.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(report, ensure_ascii=False), flush=True)

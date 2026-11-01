"""Finite, read-only USB startup observations; never opens device endpoints."""
import argparse
import json
from pathlib import Path
import subprocess
import time

USB_FIELDS = ('idVendor', 'idProduct', 'product', 'serial', 'devnum',
              'power/control', 'power/runtime_status')
SERVICES = ('guardianloop-startup.service', 'guardianloop-cyton.service',
            'guardianloop-hdmi-entry.service')
ACQUISITION_EVENTS = ('CYTON_USB_', 'CYTON_DIRECT_CONFIG:', 'CYTON_CHANNEL_ACKS_',
                      'CYTON_CONFIGURATION_WAITING:', 'CYTON_READER_FAILURE:',
                      'CYTON_RECONFIGURING:', 'CYTON_STREAM_STARTED')


def usb_devices(root):
    rows = []
    for device in sorted(root.iterdir()):
        if not (device/'idVendor').exists():
            continue
        row = {'node': device.name}
        for name in USB_FIELDS:
            try:
                row[name] = (device/name).read_text().strip()
            except FileNotFoundError:
                continue  # Removal can occur between individual sysfs reads.
        if 'idVendor' in row and 'idProduct' in row:
            rows.append(row)
    return rows


def input_status(root):
    result = {}
    path = root/'status.json'
    try:
        data = json.loads(path.read_text())
    except FileNotFoundError:
        result['status_present'] = False
    except json.JSONDecodeError:
        result['status_error'] = 'invalid_json'
    else:
        result['status_present'] = True
        result['status'] = {k: data.get(k) for k in (
            'packets_seen', 'reason', 'serial_identity', 'updated_at')}
    try:
        info = (root/'telemetry.json').stat()
    except FileNotFoundError:
        result['telemetry_present'] = False
    else:
        result.update(telemetry_present=True, telemetry_modified_at=info.st_mtime)
    return result


def command_output(arguments):
    try:
        result = subprocess.run(arguments, capture_output=True, text=True, timeout=3)
    except subprocess.TimeoutExpired:
        return {'error': 'timeout'}
    except FileNotFoundError:
        return {'error': 'command_missing'}
    if result.returncode:
        return {'returncode': result.returncode, 'error': result.stderr[:500]}
    return {'text': result.stdout}


def diagnostic_logs():
    kernel = command_output(['dmesg'])
    if 'text' in kernel:
        kernel = {'lines': [line for line in kernel['text'].splitlines()
                  if any(word in line.lower() for word in (
                      'usb ', 'ftdi', 'fpga_manager', 'hub_ext_port', 'over-current'))][-300:]}
    acquisition = command_output(['journalctl', '-b', '-u', 'guardianloop-cyton.service',
                                  '-n', '120', '--no-pager', '-o', 'short-monotonic'])
    if 'text' in acquisition:
        acquisition = {'lines': [line for line in acquisition['text'].splitlines()
                       if any(word in line for word in ACQUISITION_EVENTS)][-60:]}
    return {'kernel': kernel, 'acquisition': acquisition}


def collect(output, seconds):
    boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    output.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = output/(boot+'-'+str(time.monotonic_ns())+'.jsonl')
    started = time.monotonic()
    previous = None
    with path.open('x', encoding='utf-8') as stream:
        path.chmod(0o600)

        def record(kind, **values):
            stream.write(json.dumps(dict(kind=kind, boot=boot,
                uptime_s=time.monotonic(), **values), separators=(',', ':'))+'\n')
            stream.flush()

        record('started', planned_seconds=seconds, raw_eeg_saved=False,
               usb_endpoints_opened=False, physical_control=False,
               logs=diagnostic_logs())
        while time.monotonic()-started < seconds:
            receiver = Path('/dev/serial/by-id/usb-FTDI_FT231X_USB_UART_D309LDXY-if00-port0')
            observation = dict(usb=usb_devices(Path('/sys/bus/usb/devices')),
                receiver_ready=receiver.is_char_device(),
                receiver_target=str(receiver.resolve()), input=input_status(Path('/run/guardianloop')))
            if observation != previous:
                record('observation', **observation)
                previous = observation
            time.sleep(1)
        services = command_output(['systemctl', 'show', *SERVICES, '-p', 'Id', '-p',
            'ActiveState', '-p', 'MainPID', '-p', 'NRestarts',
            '-p', 'ExecMainStartTimestampMonotonic'])
        record('completed', elapsed_s=time.monotonic()-started,
               services=services, logs=diagnostic_logs())
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path('/var/lib/guardianloop-usb-traces'))
    parser.add_argument('--seconds', type=int, choices=range(1, 181), default=180)
    args = parser.parse_args()
    print('USB_BOOT_TRACE_SAVED '+str(collect(args.output, args.seconds)), flush=True)


if __name__ == '__main__':
    main()

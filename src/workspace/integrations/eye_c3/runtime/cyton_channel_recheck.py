"""One-shot, authorized Cyton configuration check; no raw EEG is recorded."""
import argparse
import json
import os
from pathlib import Path
import re
import select
import subprocess
import sys
import time


FORMAL = Path('/home/xilinx/jupyter_notebooks/guardianloop_pynq')
PORT = '/dev/serial/by-id/usb-FTDI_FT231X_USB_UART_D309LDXY-if00-port0'
SERVICE = 'guardianloop-cyton.service'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--soft-initialize', action='store_true')
    args = parser.parse_args()
    sys.path.insert(0, str(FORMAL))
    from cyton_guardianloop import command_response, configure_serial, write_command

    stage = Path(__file__).resolve().parent
    if not stage.name.startswith('gl-cyton-channels-20261011-'):
        raise ValueError('Refuse an unrelated diagnostic directory')
    report = {'raw_eeg_saved': False, 'commands': [], 'restored': False}
    fd = None
    attempted_stop = False

    def collect(seconds, terminator=False):
        data = bytearray()
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            if select.select([fd], [], [], .05)[0]:
                data.extend(os.read(fd, 4096))
                if len(data) > 16384:
                    raise ValueError('Unexpectedly large serial response')
                if terminator and b'$$$' in data:
                    break
        return bytes(data)

    def query_registers():
        write_command(fd, b'?')
        response = collect(3, terminator=True)
        # Retain only register lines, not any residual binary EEG stream.
        text = response.decode('ascii', errors='replace')
        lines = [line.strip() for line in text.splitlines()
                 if re.match(r'^(CH[1-8]SET|BIAS_SENS[PN]|MISC1)[,\s]', line.strip())]
        return {'complete': b'$$$' in response, 'registers': lines}

    try:
        attempted_stop = True
        subprocess.run(['systemctl', 'stop', SERVICE], check=True, timeout=20)
        if subprocess.check_output(['systemctl', 'show', SERVICE, '-p', 'MainPID',
                                    '--value'], text=True).strip() != '0':
            raise ValueError('Acquisition still owns the receiver')
        fd = os.open(PORT, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
        configure_serial(fd)
        write_command(fd, b's')
        collect(.5)
        if args.soft_initialize:
            report['soft_reset_requested'] = True
            response = command_response(fd, b'v', timeout=6.)
            report['reset_response'] = response.decode('ascii', errors='replace')[:1024]
            if b'OpenBCI' not in response or b'ADS1299' not in response:
                raise ValueError('Cyton reset did not return its device readiness banner')
            response = command_response(fd, b'd')
            report['default_settings_response'] = response.decode('ascii', errors='replace')[:512]
            if response.strip() != b'updating channel settings to default':
                raise ValueError('Cyton did not confirm default channel settings')
        report['before'] = query_registers()
        write_command(fd, b'c')
        collect(.3)
        for channel in range(1, 9):
            command = ('x%d060110X' % channel).encode('ascii')
            write_command(fd, command)
            response = collect(.75, terminator=True)
            text = response.decode('ascii', errors='replace')
            messages = re.findall(r'(?:Success: Channel set for [1-8]|'
                                  r'Failure: [A-Za-z0-9 :_-]+|'
                                  r'Timeout processing multi byte message[^$\r\n]*)', text)
            report['commands'].append({'channel': channel,
                'acknowledged': ('Success: Channel set for %d' % channel) in text,
                'response': messages[:2]})
            # Allow the board to finish the previous channel before the next one.
            collect(.1)
        report['after'] = query_registers()
        report['all_acknowledged'] = all(r['acknowledged'] for r in report['commands'])
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        report['error'] = type(error).__name__ + ': ' + str(error)
    finally:
        if fd is not None:
            os.close(fd)
        if attempted_stop:
            try:
                subprocess.run(['systemctl', 'start', SERVICE], check=True, timeout=20)
                report['restored'] = subprocess.check_output(
                    ['systemctl', 'is-active', SERVICE], text=True).strip() == 'active'
            except (OSError, subprocess.SubprocessError) as error:
                report['restore_error'] = type(error).__name__ + ': ' + str(error)
        (stage / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        print(json.dumps(report), flush=True)
    if not report['restored'] or report.get('error'):
        raise SystemExit(1)


if __name__ == '__main__':
    main()

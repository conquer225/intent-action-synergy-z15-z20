"""Finite receiver/radio connection check, without EEG quality analysis."""
import argparse
import array
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
import termios

FORMAL = '/home/xilinx/jupyter_notebooks/guardianloop_pynq'
sys.path.insert(0, FORMAL)
from cyton_guardianloop import configure_serial, write_command
from probe_cyton_raw import read_for, parse_frames


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--gui-modem-lines', action='store_true')
    parser.add_argument('--start-only', action='store_true')
    args = parser.parse_args()
    if not os.environ.get('INVOCATION_ID'):
        raise RuntimeError('Run in the recovery-protected diagnostic service')
    service = 'guardianloop-cyton.service'
    report = {'queries': [], 'eeg_saved': False, 'restored': False}
    fd = None
    original_bits = None
    stream_started = False
    try:
        subprocess.run(['systemctl', 'stop', service], check=True, timeout=35)
        pid = subprocess.check_output(['systemctl', 'show', service, '-p',
                                       'MainPID', '--value'], text=True).strip()
        if pid != '0':
            raise RuntimeError('Acquisition still owns the receiver')
        fd = os.open('/dev/serial/by-id/usb-FTDI_FT231X_USB_UART_D309LDXY-if00-port0',
                     os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
        configure_serial(fd)
        bits = array.array('i', [0])
        fcntl.ioctl(fd, termios.TIOCMGET, bits, True)
        report['modem_bits'] = bits[0]
        if args.gui_modem_lines:
            original_bits = bits[0]
            lines = array.array('i', [termios.TIOCM_DTR | termios.TIOCM_RTS])
            fcntl.ioctl(fd, termios.TIOCMBIC, lines)
            fcntl.ioctl(fd, termios.TIOCMGET, bits, True)
            report['gui_modem_bits'] = bits[0]
        write_command(fd, b's')
        read_for(fd, .5)
        if args.start_only:
            termios.tcflush(fd, termios.TCIFLUSH)
            stream_started = True
            write_command(fd, b'b')
            data = bytes(read_for(fd, 3.))
            frames, skipped = parse_frames(data)
            report['start_only'] = {'seconds': 3, 'bytes': len(data),
                                    'frames': len(frames), 'skipped_bytes': skipped}
        else:
            for name, command in (('radio_status', b'\xf0\x07'),
                                  ('radio_channel', b'\xf0\x00'), ('firmware', b'V')):
                termios.tcflush(fd, termios.TCIFLUSH)
                write_command(fd, command)
                data = bytes(read_for(fd, 2.))
                frames, _ = parse_frames(data)
                printable = all(b in (9, 10, 13) or 32 <= b <= 126 for b in data)
                report['queries'].append({'name': name, 'bytes': len(data),
                    'frames': len(frames), 'ascii': data.decode('ascii') if printable else None,
                    'reply_hex': data.hex() if not frames and len(data) < 512 else None})
    finally:
        try:
            if fd is not None:
                try:
                    if stream_started:
                        write_command(fd, b's')
                    if original_bits is not None:
                        fcntl.ioctl(fd, termios.TIOCMSET, array.array('i', [original_bits]))
                finally:
                    os.close(fd)
        finally:
            subprocess.run(['systemctl', 'start', service], check=True, timeout=35)
            report['restored'] = subprocess.check_output(
                ['systemctl', 'is-active', service], text=True).strip() == 'active'
            (Path(__file__).parent/'connection-report.json').write_text(json.dumps(report, indent=2))
            print(json.dumps(report), flush=True)


if __name__ == '__main__':
    main()

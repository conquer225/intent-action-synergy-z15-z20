"""Production service entry: MI stays off unless the root-owned opt-in is true."""
import argparse
import hashlib
import os
from pathlib import Path
import stat
import sys
import time

from cyton_trial_recorder import atomic_json
from mi_service_config import CONFIG_PATH, MODEL_NAME, MODEL_SHA256, BACKEND_HOST, BACKEND_PORT, enabled


def acquisition_args(arguments, root, config_path=CONFIG_PATH):
    if any(arg.startswith('--mi-') or arg == '--allow-experimental-mi' for arg in arguments):
        raise ValueError('The service entry controls MI through guardianloop-mi.json only')
    if any(arg.startswith('--live-primary') or arg.startswith('--isolated-primary')
           or arg == '--isolated-reader-batch' for arg in arguments):
        raise ValueError('The service entry controls primary execution through its unit environment')
    result = list(arguments)
    if not any(arg == '--port' or arg.startswith('--port=') for arg in result):
        port = os.environ.get('GL_CYTON_PORT')
        if port:
            result += ['--port', port]
    if '--wait-for-data' not in result:
        result.append('--wait-for-data')
    primary = os.environ.get('GL_PRIMARY_EXECUTION', 'sync')
    if primary not in ('sync', 'async'):
        raise ValueError('GL_PRIMARY_EXECUTION must be sync or async')
    if primary == 'async':
        result.append('--live-primary-worker')
    if enabled(config_path):
        model = Path(root) / MODEL_NAME
        if hashlib.sha256(model.read_bytes()).hexdigest() != MODEL_SHA256:
            raise ValueError('Installed experimental MI weights do not match the accepted artifact')
        result += ['--mi-experimental-model', str(model), '--allow-experimental-mi',
                   '--mi-source', 'live', '--mi-web-host', BACKEND_HOST,
                   '--mi-web-port', str(BACKEND_PORT),
                   '--mi-audit-log', str(Path(root) / 'mi-events.jsonl')]
    return result


def wait_for_receiver(arguments):
    parser = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    parser.add_argument('--port', default='/dev/ttyUSB0')
    parser.add_argument('--status-file', default='/tmp/guardianloop_status.json')
    args, _ = parser.parse_known_args(arguments)
    announced = False
    while True:
        try:
            mode = Path(args.port).stat().st_mode
        except FileNotFoundError:
            if not announced:
                print(f'CYTON_USB_WAITING: identity={args.port}', flush=True)
                announced = True
            atomic_json(Path(args.status_file), {
                'source': 'bci', 'valid': False, 'state': 'invalid', 'level': 'unknown',
                'reason': 'WAITING_FOR_USB_RECEIVER', 'updated_at': time.time(),
                'score': None, 'raw_ratio': None,
                'emotion': {'valid': False, 'state': 'stream_interrupted'},
                'serial_identity': args.port,
            })
            time.sleep(1)
            continue
        if not stat.S_ISCHR(mode):
            raise ValueError(f'Cyton serial identity is not a character device: {args.port}')
        print(f'CYTON_USB_READY: identity={args.port} node={Path(args.port).resolve()}', flush=True)
        return


def main():
    sys.argv[1:] = acquisition_args(sys.argv[1:], Path(__file__).resolve().parent)
    wait_for_receiver(sys.argv[1:])
    import cyton_guardianloop
    cyton_guardianloop.main()


if __name__ == '__main__':
    main()

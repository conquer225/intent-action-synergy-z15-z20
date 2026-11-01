"""Paced recorded-file adapter for the standalone candidate, never live EEG."""
import argparse
from http.server import ThreadingHTTPServer
from pathlib import Path
import threading
import time

import numpy as np

from mi_cued import CuedMISession
from mi_cued_server import make_handler
from mi_eegnet_portable import OfflineEEGNet


def load_recording(path):
    with np.load(path, allow_pickle=False) as data:
        raw, seq = data['recorded'].copy(), data['recorded_seq'].copy()
    if (raw.ndim != 2 or raw.shape[1] != 8 or len(raw) < 500
            or not np.isfinite(raw).all() or seq.shape != (len(raw),)
            or not np.issubdtype(seq.dtype,np.integer) or np.any(seq < 0)):
        raise ValueError('Finite recorded N×8 data and nonnegative integer packet counters required')
    return raw, seq.astype(np.int64) % 256


def feed_recording(session, raw, seq, stop, *, repeat=False):
    while not stop.is_set():
        started = time.monotonic()
        try:
            for offset in range(0,len(raw),50):
                stop_at = min(offset+50,len(raw))
                deadline = started+stop_at/250
                if stop.wait(max(0,deadline-time.monotonic())):
                    return
                # Windows timed waits may return early. Preserve late deadlines.
                received = min(deadline,time.monotonic())
                session.feed(raw[offset:stop_at],seq[offset:stop_at],
                             received_monotonic=received)
        finally:
            session.disconnect('replay_eof')
        if not repeat:
            return
        session.disconnect('replay_loop_restart')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model',type=Path,required=True)
    parser.add_argument('--input',type=Path,required=True)
    parser.add_argument('--allow-experimental',action='store_true')
    parser.add_argument('--host',default='127.0.0.1')
    parser.add_argument('--port',type=int,default=9104)
    parser.add_argument('--repeat',action='store_true',help='Repeat only this labeled recorded input')
    parser.add_argument('--audit-log',type=Path)
    args = parser.parse_args()
    if not args.allow_experimental:
        parser.error('Explicit --allow-experimental required; no production model promotion')
    model = OfflineEEGNet(args.model,allow_experimental=True)
    raw, seq = load_recording(args.input)
    session = CuedMISession(model,source='replay',log_path=args.audit_log)
    server = ThreadingHTTPServer((args.host,args.port),make_handler(session))
    stop = threading.Event()
    worker = threading.Thread(target=feed_recording,args=(session,raw,seq,stop),
                              kwargs={'repeat':args.repeat},daemon=True)
    worker.start()
    print(f'MI_RECORDED_ONLY: http://{args.host}:{args.port}/mi-cued; NEVER live/accuracy/control',flush=True)
    try:
        server.serve_forever()
    finally:
        stop.set()
        worker.join(timeout=2)
        session.disconnect('server_shutdown')
        server.server_close()


if __name__ == '__main__':
    main()

"""Live SSVEP lane fed before primary inference; never opens another USB reader."""
import math
import multiprocessing
import os
from pathlib import Path
import queue
import time

import numpy as np

from cyton_reader_sink import ReaderPacketSink
from cyton_trial_recorder import atomic_json
from ssvep_cue_runtime import SSVEPCueRuntime, BACKEND_PORT, LOG_PATH
from ssvep_shadow import SSVEPShadow, LIVE_PATH


def consume_packets(pending, stopped, shadow, decoder, multiplier, batch_samples=1):
    previous = None
    while not stopped.is_set():
        try:
            message = pending.get(timeout=.1)
        except queue.Empty:
            shadow.idle()
            continue
        for ordinal, packet, malformed, received_at in ((message,) if batch_samples == 1 else message):
            if previous is not None and ordinal != previous+1:
                shadow.gaps += 1
                shadow.disconnect('ssvep_reader_queue_gap')
            previous = ordinal
            age = time.monotonic()-received_at
            if not math.isfinite(age) or age < 0 or age > .5:
                # Age is checked per packet, not against the newest batch member.
                shadow.disconnect('input_backlog', publish=shadow.latest.get('reason') != 'input_backlog')
                continue
            counts = np.asarray(decoder(packet))
            if counts.shape != (8,):
                raise ValueError('Expected eight ADC channels')
            shadow.packet(counts.astype(np.float64)*multiplier, packet[1], bool(malformed),
                          now=received_at, adc_rails=np.abs(counts[6:8].astype(np.float64)) >= (2**23-1)*.99)


def _worker(connection, pending, stopped, protocol, coefficients, channel_map,
            decoder, multiplier, status_path, log_path, record_status_path, port,
            page_policy_path=None, reader_batch_samples=1):
    cue = shadow = None
    ready = False
    reason = 'service_stopped_or_stream_timeout'
    try:
        cue = SSVEPCueRuntime(log_path=log_path, port=port, record_status_path=record_status_path,
                             input_transport='bounded_serial_reader_tap', page_policy_path=page_policy_path)
        shadow = SSVEPShadow(protocol, coefficients, channel_map, status_path=status_path,
                             event_sink=cue.observe)
        if page_policy_path:
            from page_policy import ScheduledLane
            shadow=ScheduledLane(shadow,page_policy_path,'ssvep_candidate',
                                 mode='live_readonly_hdmi',standalone_tasks=('ssvep_candidate',))
        connection.send(dict(ready=True, port=cue.server.server_port))
        ready = True
        consume_packets(pending, stopped, shadow, decoder, multiplier, reader_batch_samples)
    except (OSError, ValueError, KeyError, FloatingPointError, np.linalg.LinAlgError) as exc:
        reason = 'ssvep_reader_worker_error'
        if not ready:
            connection.send(dict(ready=False, error='%s: %s' % (type(exc).__name__, exc)))
        print('SSVEP_READER_DISABLED: %s: %s' % (type(exc).__name__, exc), flush=True)
    finally:
        try:
            if shadow is not None:
                shadow.disconnect(reason)
        finally:
            if cue is not None:
                cue.close()
            connection.close()


class SSVEPReaderRuntime:
    def __init__(self, protocol, coefficients, channel_map, decoder, multiplier,
                 status_path=LIVE_PATH, log_path=LOG_PATH, record_status_path=None,
                 port=BACKEND_PORT, queue_capacity=128, page_policy_path=None, reader_batch_samples=1):
        if not math.isfinite(multiplier) or multiplier <= 0:
            raise ValueError('Invalid ADC scaling')
        self.path = Path(status_path)
        self.closed = False
        context = multiprocessing.get_context('spawn')
        self.reader_sink = ReaderPacketSink(context, queue_capacity, batch_samples=reader_batch_samples)
        page_policy_path=page_policy_path or os.environ.get('GL_PAGE_POLICY_PATH')
        self.stopped = context.Event()
        receive, send = context.Pipe(duplex=False)
        worker_args=(send,self.reader_sink.pending,self.stopped,str(protocol),str(coefficients),
                     tuple(channel_map),decoder,multiplier,str(self.path),log_path,record_status_path,port)
        if page_policy_path:
            from page_policy import ScheduledSink
            self.reader_sink=ScheduledSink(self.reader_sink,page_policy_path,'ssvep_candidate',
                                          mode='live_readonly_hdmi',standalone_tasks=('ssvep_candidate',))
        worker_args+=(str(page_policy_path) if page_policy_path else None, reader_batch_samples)
        self.process = context.Process(target=_worker, name='ssvep-reader-consumer', daemon=True,
            args=worker_args)
        self.process.start()
        send.close()
        try:
            if not receive.poll(35):
                raise OSError('SSVEP worker startup timed out')
            result = receive.recv()
            if not result['ready']:
                raise OSError(result['error'])
            self.port = result['port']
        except (OSError, EOFError):
            self.close()
            raise
        finally:
            receive.close()

    def close(self):
        if self.closed:
            return
        self.closed = True
        self.stopped.set()
        self.process.join(timeout=3)
        if self.process.is_alive():
            self.process.terminate()
            self.process.join(timeout=2)
        self.reader_sink.close()
        atomic_json(self.path, dict(state='no_data', valid=False, source='live',
            frequency_hz=None, control_enabled=False, input_age_seconds=0.,
            updated_at=time.time(), updated_monotonic=time.monotonic(), reason='ssvep_worker_closed'))

"""Optional bounded MI consumer of the main reader's decoded packets."""
from http.server import HTTPServer
from pathlib import Path
import math
import multiprocessing
import queue
import threading
import time
from types import SimpleNamespace

import numpy as np

from mi_cued import CuedMISession, FRESH_SECONDS
from mi_rms_live_virtual import make_handler, create_session
from mi_features import CHANNELS
from cyton_reader_sink import ReaderPacketSink


class MIAcquisition:
    def __init__(self, session):
        self.session = session
        self.pending = queue.Queue(maxsize=2)
        self.state_lock = threading.RLock()
        self.rows, self.sequences, self.stamps = [], [], []
        self.multiplier = 1.
        self.generation = 0
        self.error = None
        self.closed = False
        self.stats = dict(packets=0, batches=0, queue_full=0, stale_batches=0)
        self.worker = threading.Thread(target=self._run, name='mi-packet-consumer', daemon=True)
        self.worker.start()

    def interrupt(self, reason):
        with self.state_lock:
            self.generation += 1
            self.rows.clear(); self.sequences.clear(); self.stamps.clear()
            while True:
                try:
                    self.pending.get_nowait()
                    self.pending.task_done()
                except queue.Empty:
                    break
        self.session.disconnect(reason)

    def packet(self, raw_values, sequence, malformed, *, received_at, microvolts_per_count=1.):
        row = np.asarray(raw_values)
        if (malformed or row.shape != (8,)
                or type(sequence) not in (int, np.uint8) or not 0 <= int(sequence) <= 255
                or not math.isfinite(received_at) or received_at > self.session.clock()
                or not math.isfinite(microvolts_per_count) or microvolts_per_count <= 0):
            self.interrupt('malformed_acquisition_packet')
            return
        if microvolts_per_count != self.multiplier:
            self.interrupt('acquisition_gain_changed')
            self.multiplier = microvolts_per_count
        overflow = False
        with self.state_lock:
            if self.closed or self.error:
                return
            self.stats['packets'] += 1
            self.rows.append(row.copy()); self.sequences.append(int(sequence)); self.stamps.append(received_at)
            if len(self.rows) == 50:
                batch = (self.generation, np.asarray(self.rows), np.asarray(self.sequences),
                         self.stamps[0], self.stamps[-1], self.multiplier)
                self.rows.clear(); self.sequences.clear(); self.stamps.clear()
                try:
                    self.pending.put_nowait(batch)
                except queue.Full:
                    self.stats['queue_full'] += 1
                    overflow = True
        if overflow:
            self.interrupt('mi_queue_full')

    def _run(self):
        while True:
            batch = self.pending.get()
            try:
                if batch is None:
                    return
                generation, raw, sequences, first_stamp, last_stamp, multiplier = batch
                with self.session.lock:
                    with self.state_lock:
                        if generation != self.generation or self.error:
                            continue
                    if self.session.clock() - first_stamp > FRESH_SECONDS:
                        self.stats['stale_batches'] += 1
                        self.interrupt('mi_oldest_packet_stale')
                    else:
                        values = raw.astype(np.float64) * multiplier
                        self.session.feed(values, sequences, received_monotonic=float(last_stamp))
                        self.stats['batches'] += 1
            except (OSError, ValueError, FloatingPointError) as exc:
                self.error = f'{type(exc).__name__}: {exc}'
                try:
                    self.session.disconnect('mi_adapter_error')
                except OSError as log_error:
                    self.error += '; withdrawal log: '+str(log_error)
            finally:
                self.pending.task_done()

    def idle(self, now):
        with self.state_lock:
            partial_stale = bool(self.stamps and now-self.stamps[0] > FRESH_SECONDS)
        if partial_stale:
            self.interrupt('mi_partial_batch_stale')
        with self.session.lock:
            if self.session.last_received is not None and now-self.session.last_received > FRESH_SECONDS:
                self.interrupt('transport_disconnected')

    def close(self):
        with self.state_lock:
            if self.closed:
                return
            self.closed = True
        try:
            self.interrupt('acquisition_stopped')
        finally:
            self.pending.put(None)
            self.worker.join(timeout=3)
            if self.worker.is_alive():
                raise RuntimeError('MI consumer did not terminate')


def task_status(paths, source):
    import json
    result = {}
    for name, path in paths.items():
        try:
            value = json.loads(Path(path).read_text(encoding='utf-8'))
            age = time.time()-float(value.get('updated_at', 0))
            fields = ('state', 'valid', 'reason', 'level', 'score', 'class_id', 'label',
                      'frequency_hz', 'calibration_current', 'calibration_total',
                      'accepted_windows', 'warmup_samples', 'required_samples',
                      'updated_at', 'input_age_seconds')
            summary = {key: value[key] for key in fields if key in value}
            summary.update(source=source, control_enabled=False)
            if name == 'primary':
                emotion = value.get('emotion') or {}
                summary['emotion'] = {key: emotion[key] for key in
                                      ('state', 'valid', 'label', 'reason') if key in emotion}
            result[name] = dict(payload=summary if 0 <= age <= 2 else {}, stale=not 0 <= age <= 2)
        except (OSError, ValueError, TypeError):
            result[name] = dict(payload={}, stale=True)
    return dict(source=source, real=source=='live', control_enabled=False, tasks=result)


class CandidateHTTPServer(HTTPServer):
    # Session commands are already serialized. Reuse one request thread instead
    # of creating a new OS thread for every polling/heartbeat request.
    def get_request(self):
        connection, address = super().get_request()
        connection.settimeout(.5)
        return connection, address


class RemoteMISession:
    """One trusted pipe, with a bounded response wait and fail-closed cache."""
    clock = staticmethod(time.monotonic)

    def __init__(self, connection, initial):
        self.connection=connection
        self.lock=threading.RLock()
        self.cached=initial
        self.last_received=None
        self.error=None
        self.closed=False

    def request(self, action, **fields):
        with self.lock:
            if self.closed:
                raise OSError('MI worker connection is closed')
            try:
                self.connection.send(dict(action=action,**fields))
                if not self.connection.poll(.5):
                    raise OSError('MI worker response timeout')
                response=self.connection.recv()
            except (OSError, EOFError) as exc:
                self.error=f'{type(exc).__name__}: {exc}'
                self.closed=True
                self.connection.close()
                self.last_received=None
                self.cached=dict(self.cached, result=None,input_state='no_data',
                                 state='rejected',reason='mi_worker_disconnected',received_samples=0)
                raise OSError(self.error) from exc
            self.cached=response['snapshot']
            self.last_received=response['last_received']
            if response.get('error'):
                raise ValueError(response['error'])
            return self.cached

    def feed(self, values, sequences, *, received_monotonic):
        return self.request('feed',values=values,sequences=sequences,received=received_monotonic)

    def disconnect(self, reason):
        if self.closed:
            return self.cached
        try:
            return self.request('disconnect',reason=reason)
        except OSError:
            return self.cached

    def snapshot(self):
        if self.closed:
            return self.cached
        try:
            return self.request('snapshot')
        except OSError:
            return self.cached


def _forward_reader_packets(pending, adapter, decoder, multiplier, stopped):
    previous = None
    try:
        while not stopped.is_set():
            try:
                ordinal, packet, malformed, received_at = pending.get(timeout=.1)
            except queue.Empty:
                adapter.idle(adapter.session.clock())
                continue
            # Counter bytes can wrap after exactly 256 lost packets. The local
            # unbounded ordinal also detects these losses from a full tap queue.
            if previous is not None and ordinal != previous + 1:
                adapter.interrupt('mi_reader_queue_gap')
            previous = ordinal
            adapter.packet(decoder(packet), packet[1], malformed,
                           received_at=received_at, microvolts_per_count=multiplier)
    except (OSError, ValueError, FloatingPointError) as exc:
        adapter.error = '%s: %s' % (type(exc).__name__, exc)
        adapter.interrupt('mi_reader_tap_error')


def _mi_worker(connection, model_path, source, host, port, log_path, status_paths, audit_directory,
               reader_pending, packet_decoder, microvolts_per_count):
    server=thread=None
    audit=None
    adapter = reader_thread = None
    reader_stopped = threading.Event()
    try:
        if audit_directory is not None:
            from mi_worker_audit import MIWorkerAudit
            audit=MIWorkerAudit(audit_directory)
        session=create_session(model_path,source=source,log_path=log_path)
        if reader_pending is not None:
            adapter = MIAcquisition(session)
            reader_thread = threading.Thread(target=_forward_reader_packets,
                args=(reader_pending, adapter, packet_decoder, microvolts_per_count, reader_stopped),
                name='mi-reader-tap', daemon=True)
            reader_thread.start()
        server=CandidateHTTPServer((host,port),make_handler(session,
                    multitask=lambda:task_status(status_paths,source)))
        thread=threading.Thread(target=server.serve_forever,name='mi-worker-http',daemon=True)
        thread.start()
        connection.send(dict(port=server.server_port,snapshot=session.snapshot()))
        while True:
            try:
                request=connection.recv()
            except EOFError:
                break
            action=request['action']
            error=None
            try:
                if action=='feed':
                    session.feed(request['values'],request['sequences'],
                                 received_monotonic=float(request['received']))
                elif action in ('disconnect','close'):
                    session.disconnect(request.get('reason','acquisition_stopped'))
                elif action!='snapshot':
                    raise ValueError('Unknown trusted MI worker operation')
            except (OSError,ValueError,FloatingPointError) as exc:
                error=f'{type(exc).__name__}: {exc}'
            connection.send(dict(snapshot=session.snapshot(),last_received=session.last_received,error=error))
            if action=='close':
                break
    except (OSError,ValueError,FloatingPointError) as exc:
        try:
            connection.send(dict(startup_error=f'{type(exc).__name__}: {exc}'))
        except OSError:
            pass
    finally:
        reader_stopped.set()
        if reader_thread is not None:
            reader_thread.join(timeout=2)
        if adapter is not None:
            adapter.close()
        if server is not None:
            if thread is not None and thread.is_alive():
                server.shutdown(); thread.join(timeout=3)
            server.server_close()
        if audit is not None:
            audit.save()
        connection.close()


class MICandidateRuntime:
    def __init__(self, model_path, channels, *, source, host, port, log_path, status_paths,
                 audit_directory=None, packet_decoder=None, microvolts_per_count=1.):
        if tuple(channels) != CHANNELS:
            raise ValueError('MI requires exactly the fixed eight physical positions')
        context=multiprocessing.get_context('spawn')
        parent,child=context.Pipe()
        self.reader_sink = ReaderPacketSink(context) if packet_decoder is not None else None
        self.thread=context.Process(target=_mi_worker,args=(child,str(model_path),source,host,port,
                log_path,status_paths,audit_directory,
                self.reader_sink.pending if self.reader_sink is not None else None,
                packet_decoder,microvolts_per_count),name='mi-stream-worker',daemon=True)
        self.thread.start(); child.close()
        try:
            if not parent.poll(35):
                raise RuntimeError('MI worker did not initialize')
            ready=parent.recv()
            if 'startup_error' in ready:
                raise ValueError(ready['startup_error'])
            self.session=RemoteMISession(parent,ready['snapshot'])
            self.server=SimpleNamespace(server_port=ready['port'])
            self.adapter = None if self.reader_sink is not None else MIAcquisition(self.session)
        except (OSError,EOFError,RuntimeError,ValueError):
            parent.close()
            self.thread.join(timeout=2)
            if self.thread.is_alive():
                self.thread.terminate(); self.thread.join(timeout=3)
            if self.reader_sink is not None:
                self.reader_sink.close()
            raise
        print(f'MI_EXPERIMENTAL_ENTRY: http://{host}:{self.server.server_port}/ ; source={source}; '
              'worker=isolated_ARM_process; control=false',flush=True)

    def close(self):
        try:
            if self.adapter is not None:
                self.adapter.close()
        finally:
            try:
                if not self.session.closed:
                    self.session.request('close')
            finally:
                self.session.closed=True
                self.session.connection.close()
                # Replay numerical export is outside active packet processing.
                self.thread.join(timeout=20)
                if self.thread.is_alive():
                    self.thread.terminate(); self.thread.join(timeout=3)
                    raise RuntimeError('MI worker failed to stop normally')
                if self.reader_sink is not None:
                    self.reader_sink.close()

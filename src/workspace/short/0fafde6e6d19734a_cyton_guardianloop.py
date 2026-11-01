#!/usr/bin/env python3
"""Run GuardianLoop directly from an OpenBCI Cyton USB dongle on the Z15."""

import argparse
import errno
import fcntl
import json
import math
import multiprocessing
import os
import queue
import re
import select
import signal
import termios
import time
import urllib.error
import urllib.request
from collections import deque
from contextlib import closing
from pathlib import Path

import numpy as np

from guardianloop_pynq import CHANNELS, WINDOW_SAMPLES, GuardianLoopPynq
from cyton_sqi import CausalEEGFilter, CytonSQIMonitor, GameemoEmotionRecognizer, segmented_sqi, primary_windows
from pl_causal_filter import KernelOwnedCausalFilter
from cyton_covariance import CovarianceFeatureStream, CovarianceSVM
from cyton_trial_recorder import TrialRecorder
from cyton_fatigue import FourChannelFatigue
from seed_shadow import SeedShadow, LIVE_PATH
from ssvep_shadow import LIVE_PATH as SSVEP_PATH
from ssvep_acquisition import SSVEPReaderRuntime
from cyton_reader_sink import decode_eeg_counts
from cyton_trial_recorder import atomic_json, STATUS_PATH as RECORDING_STATUS_PATH
from calibration_session import CalibrationSession
from wear_session import WearSession
from telemetry_json import WaveformJSONCache
from primary_window import PrimaryWindowProcessor, FATIGUE_MODEL_CHANNEL_MAP


PACKET_BYTES = 33
START_BYTE = 0xA0
DEFAULT_UV_PER_COUNT = 4_500_000.0 / 24.0 / (2**23 - 1)
DEFAULT_CHANNEL_MAP = ("F3", "F4", "C3", "C4", "T7", "T8", "O1", "O2")
MAX_PROCESSING_AGE_SECONDS = .5


def fatigue_payload(result, calibrated):
    state = str(result.get("state", "INVALID")).lower()
    prediction = bool(result.get("valid")) and state in ("normal", "mild", "severe")
    return {
        "source": "bci",
        "valid": prediction,
        "level": state if prediction else "unknown",
        "state": "prediction" if prediction else (
            "calibrating" if state == "calibrating" else "invalid"),
        "seq": int(result.get("window", 0)),
        "score": result.get("smoothed_perclos"),
        "raw_ratio": result.get("perclos"),
        "window_seconds": 8,
        "window_hop_seconds": int(result.get("window_hop_seconds", 2 if calibrated else 8)),
        "calibration_current": int(result.get("calibration_current", 0)),
        "calibration_total": int(result.get("calibration_total", 15)),
        "algorithm_version": result.get("algorithm_version", "guardianloop-pynq-pl-v1"),
        "updated_at": int(time.time()),
        "signal_quality": result.get("signal_quality"),
        "sqi": result.get("sqi"),
        "raw_interference": result.get("raw_interference"),
        "emotion": result.get("emotion"),
        "reason": result.get("reason"),
        "packets_seen": int(result.get("packets_seen", 0)),
        "dropped_packets": int(result.get("dropped_packets", 0)),
        "sequence_gaps": int(result.get("sequence_gaps", 0)),
        "unresolved_gaps": int(result.get("unresolved_gaps", 0)),
        "malformed_bytes": int(result.get("malformed_bytes", 0)),
        "clipped_rows": int(result.get("clipped_rows", 0)),
        "channel_map": result.get("channel_map"),
        "filter_backend": result.get("filter_backend", "arm"),
        "calibration_retained": bool(result.get("calibration_retained", False)),
    }


def publish_result(result, calibrated, status_file, esp32_url, input_age_seconds=None):
    payload = fatigue_payload(result, calibrated)
    if input_age_seconds is not None:
        payload['input_age_at_prediction_seconds'] = float(input_age_seconds)
        if input_age_seconds > 3:
            payload.update(valid=False, level='unknown', score=None, raw_ratio=None,
                           reason='PROCESSING_BACKLOG', state='invalid',
                           emotion={'valid':False, 'state':'processing_backlog'})
    encoded = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8")
    if status_file:
        path = Path(status_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_bytes(encoded + b"\n")
        temporary.replace(path)
    if esp32_url:
        endpoint = esp32_url.rstrip("/") + "/api/bci/fatigue"
        request = urllib.request.Request(
            endpoint, data=encoded, headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=1.5) as response:
                print(f"ESP32_POST_OK: status={response.status} seq={payload['seq']}", flush=True)
        except (OSError, urllib.error.URLError) as exc:
            print(f"ESP32_POST_SKIPPED: {exc}", flush=True)


def publish_telemetry(samples, raw_samples, sample_index, path, packets_seen,
                      dropped_packets, sequence_gaps, unresolved_gaps, malformed_bytes,
                      clipped_rows, sqi=None, emotion=None, snapshot_time=None, diagnostics=None,
                      waveform_cache=None):
    if not path or len(samples) == 0:
        return
    total = packets_seen + dropped_packets
    payload = {
        "source": "cyton_usb",
        "real": True,
        "updated_at": time.time() if snapshot_time is None else snapshot_time,
        "sample_rate_hz": 125,
        "channels": CHANNELS,
        "sample_index": sample_index,
        "packets_seen": packets_seen,
        "dropped_packets": dropped_packets,
        "packet_loss_percent": (100.0 * dropped_packets / total) if total and not unresolved_gaps else None,
        "sequence_gaps": sequence_gaps,
        "unresolved_gaps": unresolved_gaps,
        "malformed_bytes": malformed_bytes,
        "clipped_rows": clipped_rows,
        "sqi": sqi,
        "emotion": emotion,
        "channel_map": list(DEFAULT_CHANNEL_MAP),
        "runtime": diagnostics,
    }
    if waveform_cache is None:
        payload.update(samples=np.round(np.asarray(samples), 3).tolist(),
                       raw_samples=np.round(np.asarray(raw_samples), 3).tolist())
        encoded = json.dumps(payload, separators=(',', ':'), allow_nan=False)
    else:
        filtered_json, raw_json = waveform_cache.encode(samples, raw_samples, sample_index)
        encoded = (json.dumps(payload, separators=(',', ':'), allow_nan=False)[:-1]
                   + ',"samples":' + filtered_json + ',"raw_samples":' + raw_json + '}')
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.write_text(encoded, encoding="utf-8")
    temporary.replace(destination)


def _telemetry_worker(pending):
    waveform_cache = WaveformJSONCache()
    while True:
        args = pending.get()
        if args is None:
            return
        publish_telemetry(*args, waveform_cache=waveform_cache)


class TelemetryWriter:
    """A bounded display-only queue; acquisition/model inputs never pass through it."""
    def __init__(self):
        context = multiprocessing.get_context('fork')
        self.pending = context.Queue(maxsize=1)
        self.worker = context.Process(target=_telemetry_worker, args=(self.pending,),
                                      name='cyton-telemetry-writer', daemon=True)
        self.skipped = 0
        self.worker.start()

    def submit(self, samples, raw_samples, *args, diagnostics=None):
        if not self.worker.is_alive():
            raise RuntimeError('Telemetry writer stopped')
        info = dict(diagnostics or {}, display_snapshots_skipped=self.skipped)
        snapshot = (np.array(samples, copy=True), np.array(raw_samples, copy=True)) + args + (time.time(), info)
        try:
            self.pending.put_nowait(snapshot)
        except queue.Full:
            self.skipped += 1

    def close(self):
        try:
            if self.worker.is_alive():
                try:
                    self.pending.put(None, timeout=2)
                except queue.Full:
                    pass
                self.worker.join(timeout=3)
                if self.worker.is_alive():
                    self.worker.terminate()
                    self.worker.join(timeout=1)
        finally:
            self.pending.cancel_join_thread()
            self.pending.close()


def configure_serial(fd):
    # Prevent another client from opening this receiver during acquisition.
    fcntl.ioctl(fd, termios.TIOCEXCL)
    attrs = termios.tcgetattr(fd)
    attrs[0] = 0
    attrs[1] = 0
    attrs[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
    attrs[3] = 0
    attrs[4] = termios.B115200
    attrs[5] = termios.B115200
    attrs[6][termios.VMIN] = 0
    attrs[6][termios.VTIME] = 0
    termios.tcsetattr(fd, termios.TCSANOW, attrs)
    termios.tcflush(fd, termios.TCIOFLUSH)


def write_command(fd, command):
    if os.write(fd, command) != len(command):
        raise OSError('Incomplete Cyton command write')
    termios.tcdrain(fd)


def command_response(fd, command, timeout=3.):
    termios.tcflush(fd, termios.TCIFLUSH)
    write_command(fd, command)
    response = bytearray()
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        ready, _, _ = select.select([fd], [], [], max(0., deadline-time.monotonic()))
        if not ready:
            break
        response.extend(os.read(fd, 4096))
        if len(response) > 8192:
            raise ValueError('Oversize Cyton configuration response')
        if b'$$$' in response:
            return bytes(response).split(b'$$$', 1)[0]
    raise TimeoutError('Cyton configuration acknowledgement not received')


class CytonConfigurationError(ValueError):
    """A channel command did not receive its matching success acknowledgement."""


def configure_eeg_channels(fd):
    """Put every Cyton channel in the referential EEG configuration.

    OpenBCI GUI applies these settings when it connects, but a direct serial
    client cannot rely on whatever volatile state a previous program left in
    the board.  The seven channel fields are power=on, gain=24, input=normal,
    include-in-bias=yes, SRB2=on, and SRB1=off.
    """
    # Prove the device is online before sending multibyte settings to its radio.
    version = command_response(fd, b'V').strip()
    if re.fullmatch(rb'v3\.\d+\.\d+', version) is None:
        raise ValueError('Cyton firmware did not confirm the v3 command contract')
    write_command(fd, b'c')
    time.sleep(.1)
    for channel in range(1, CHANNELS + 1):
        response = command_response(fd, f'x{channel}060110X'.encode('ascii'))
        if response.strip() != f'Success: Channel set for {channel}'.encode('ascii'):
            raise CytonConfigurationError('Cyton did not confirm channel %d settings' % channel)
    report = dict(firmware=version.decode('ascii'), acknowledged_channels=list(range(1, CHANNELS+1)))
    print('CYTON_CHANNEL_ACKS_VERIFIED: '+json.dumps(report, sort_keys=True), flush=True)
    return report


class CytonReaderError(RuntimeError):
    """Terminal serial-reader failure with no raw EEG in the diagnostic."""

    def __init__(self, report):
        self.report = report
        super().__init__('CYTON_READER_FAILURE: ' + json.dumps(report, sort_keys=True))


class _ReconfigureStream(RuntimeError):
    pass


def configured_packets(fd, timeout, *, on_idle, on_configured, on_reconfigure,
                       wait_for_data=False, **reader_options):
    """Reconfigure only after the sole serial reader has released the descriptor."""
    zero_retry_used = False
    while True:
        write_command(fd, b's')
        time.sleep(1.)
        try:
            configure_eeg_channels(fd)
        except (TimeoutError, CytonConfigurationError) as error:
            if not wait_for_data:
                raise
            on_reconfigure('CHANNEL_CONFIGURATION_UNCONFIRMED')
            print('CYTON_CONFIGURATION_WAITING: '+str(error), flush=True)
            on_idle(time.monotonic())
            time.sleep(1.)
            continue
        time.sleep(.5)
        termios.tcflush(fd, termios.TCIFLUSH)
        write_command(fd, b'b')
        on_configured()
        last_packet = time.monotonic()
        checked = 0
        zero_mask = np.ones(CHANNELS, dtype=bool)
        previous = None

        def idle(now):
            on_idle(now)
            if wait_for_data and now-last_packet >= max(5., timeout):
                raise _ReconfigureStream('CYTON_NO_PACKETS_RECONNECT')

        try:
            with closing(packets(fd, timeout, with_timing=True, on_idle=idle,
                                 wait_for_data=wait_for_data, **reader_options)) as reader:
                for packet, malformed, received_at in reader:
                    last_packet = time.monotonic()
                    # Keep recording/counters intact even for the last suspect packet.
                    yield packet, malformed, received_at
                    if checked < 250:
                        sequence = packet[1]
                        if malformed or (previous is not None and ((sequence-previous)&255) != 1):
                            checked = 0
                            zero_mask[:] = True
                        else:
                            zero_mask &= decode_eeg_counts(packet) == 0
                            checked += 1
                        previous = sequence
                        if checked == 250:
                            zeros = (np.flatnonzero(zero_mask)+1).tolist()
                            print('CYTON_CHANNEL_INPUT_CHECK: '+json.dumps(dict(
                                samples=checked, exact_zero_channels=zeros,
                                configuration_acknowledged=True)), flush=True)
                            # One broken electrode must not cause repeated whole-stream resets.
                            if wait_for_data and len(zeros) >= 2 and not zero_retry_used:
                                zero_retry_used = True
                                raise _ReconfigureStream('CYTON_MULTIPLE_ZERO_CHANNELS')
            return
        except _ReconfigureStream as error:
            reason = str(error)
            if reason == 'CYTON_NO_PACKETS_RECONNECT':
                zero_retry_used = False
        except CytonReaderError as error:
            if not wait_for_data or error.report['kind'] != 'device_restarted':
                raise
            reason = 'CYTON_DEVICE_RESTARTED'
            zero_retry_used = False
        on_reconfigure(reason)
        print('CYTON_RECONFIGURING: '+reason, flush=True)


def validate_live_primary(args, channel_map):
    root = Path('/home/xilinx/jupyter_notebooks/guardianloop_pynq')
    serial = '/dev/serial/by-id/usb-FTDI_FT231X_USB_UART_D309LDXY-if00-port0'
    if (args.port != serial or args.filter_backend != 'arm' or not args.wait_for_data
            or args.windows != 0 or args.esp32_url or channel_map != DEFAULT_CHANNEL_MAP
            or args.microvolts_per_count != DEFAULT_UV_PER_COUNT
            or Path(args.status_file) != Path('/run/guardianloop/status.json')
            or Path(args.telemetry_file) != Path('/run/guardianloop/telemetry.json')
            or Path(args.fatigue_model).resolve() != root / 'cyton_fatigue_overlap4.json'
            or Path(args.covariance_model).resolve() != root / 'gameemo_covariance_svm.npz'
            or args.isolated_primary_worker or args.isolated_reader_batch
            or args.isolated_primary_checkpoint):
        raise ValueError('Live primary worker requires the pinned fixed-eight ARM service contract')


def packets(fd, timeout, with_timing=False, on_idle=None, *, queue_capacity=8192,
            read_chunk=os.read, packet_sink=None, packet_sinks=(), wait_for_data=False,
            reader_batch_samples=1):
    if reader_batch_samples not in (1, 10) or queue_capacity < reader_batch_samples:
        raise ValueError('Reader batch must be 1 or 10 and fit the packet capacity')
    context = multiprocessing.get_context("fork")
    pending = context.Queue(maxsize=queue_capacity // reader_batch_samples)
    stopped = context.Event()
    error_recv, error_send = context.Pipe(duplex=False)
    error_ready = context.RawValue('b', 0)
    sinks = tuple(packet_sinks) + ((packet_sink,) if packet_sink is not None else ())
    tap_flushes = [sink.flush for sink in sinks
                   if getattr(sink, 'batch_samples', 1) != 1]

    def read_serial():
        error_recv.close()
        buffer = bytearray()
        malformed = 0
        locked = False
        reads = bytes_read = packets_queued = empty_reads = 0
        dispatches = 0
        batch = []
        boot_text = bytearray()

        def inspect_nonpacket(data):
            boot_text.extend(data)
            del boot_text[:-512]
            if (b'OpenBCI V3' in boot_text and b'ADS1299 Device ID:' in boot_text
                    and b'$$$' in boot_text):
                raise RuntimeError('Cyton restarted; channel configuration must be reapplied')

        def dispatch():
            nonlocal packets_queued, dispatches
            if batch:
                pending.put_nowait(batch[0] if reader_batch_samples == 1 else tuple(batch))
                packets_queued += len(batch)
                dispatches += 1
                batch.clear()

        try:
            while not stopped.is_set():
                readable, _, _ = select.select([fd], [], [], .04 if tap_flushes else .2)
                if not readable:
                    if buffer and b'OpenBCI V3' in boot_text:
                        inspect_nonpacket(buffer)
                        buffer.clear()
                    for flush in tap_flushes:
                        flush()
                    continue
                try:
                    chunk = read_chunk(fd, 8192)
                    received_at = time.monotonic()
                except OSError as exc:
                    if exc.errno in (errno.EAGAIN, errno.EWOULDBLOCK):
                        continue
                    raise
                if not chunk:
                    if not stopped.is_set():
                        empty_reads += 1
                        if empty_reads >= 3:
                            raise EOFError('serial input returned repeated EOF')
                        time.sleep(.01)
                        continue
                    break
                empty_reads = 0
                reads += 1
                bytes_read += len(chunk)
                buffer.extend(chunk)
                while len(buffer) >= PACKET_BYTES:
                    start = buffer.find(bytes((START_BYTE,)))
                    if start < 0:
                        inspect_nonpacket(buffer)
                        malformed += len(buffer)
                        buffer.clear()
                        break
                    if start:
                        inspect_nonpacket(buffer[:start])
                        malformed += start
                        del buffer[:start]
                        locked = False
                    if len(buffer) < PACKET_BYTES:
                        break
                    if buffer[32] & 0xF0 != 0xC0:
                        malformed += 1
                        del buffer[0]
                        locked = False
                        continue
                    if not locked:
                        if len(buffer) < 2 * PACKET_BYTES:
                            break
                        if (buffer[PACKET_BYTES] != START_BYTE or
                                buffer[2 * PACKET_BYTES - 1] & 0xF0 != 0xC0):
                            malformed += 1
                            del buffer[0]
                            continue
                        locked = True
                    packet = bytes(buffer[:PACKET_BYTES])
                    boot_text.clear()
                    for sink in packet_sinks:
                        sink.offer(packet, malformed, received_at)
                    if packet_sink is not None:
                        packet_sink.offer(packet, malformed, received_at)
                    batch.append((packet, malformed, received_at))
                    if len(batch) == reader_batch_samples:
                        dispatch()
                    del buffer[:PACKET_BYTES]
                    malformed = 0
                # Flush a short read immediately: no timer or extra sample wait.
                dispatch()
                # Taps reserve slots for ten packets. Flushing each short USB
                # read would turn their packet capacity into a few message slots.
        except Exception as exc:
            kind = ('device_restarted' if b'OpenBCI V3' in boot_text and b'ADS1299 Device ID:' in boot_text and b'$$$' in boot_text else
                    'queue_full' if isinstance(exc, queue.Full) else
                    'serial_eof' if isinstance(exc, EOFError) else
                    'serial_io_error' if isinstance(exc, OSError) else 'reader_exception')
            report = dict(kind=kind, errno=getattr(exc, 'errno', None),
                          exception=type(exc).__name__, reads=reads,
                          bytes_read=bytes_read, packets_queued=packets_queued,
                          malformed_pending=malformed, empty_reads=empty_reads,
                          queue_dispatches=dispatches, reader_batch_samples=reader_batch_samples)
            try:
                error_send.send(report)
                error_ready.value = 1
            except (BrokenPipeError, OSError):
                pass
        finally:
            for flush in tap_flushes:
                flush()
            error_send.close()
            if stopped.is_set():
                pending.cancel_join_thread()
            else:
                # Queue.put_nowait hands frames to a feeder thread. Flush every
                # accepted frame before the child exits; otherwise EOF can make
                # the parent lose the tail and misdiagnose a healthy replay.
                pending.close()
                pending.join_thread()

    reader = context.Process(target=read_serial, name="cyton-serial-reader", daemon=True)
    reader.start()
    error_send.close()
    last_yield = time.monotonic()
    failure = None

    def check_failure():
        nonlocal failure
        if (failure is None and (reader_batch_samples == 1 or error_ready.value)
                and error_recv.poll()):
            try:
                failure = error_recv.recv()
            except EOFError:
                pass
        # Keep terminal faults ahead of buffered frames, even within a batch.
        if failure is not None and failure['kind'] != 'serial_eof':
            raise CytonReaderError(failure)

    try:
        while True:
            check_failure()
            try:
                message = pending.get(timeout=min(timeout, .25))
                items = (message,) if reader_batch_samples == 1 else message
                for item in items:
                    if reader_batch_samples != 1:
                        check_failure()
                    last_yield = time.monotonic()
                    yield item if with_timing else item[:2]
            except queue.Empty:
                if failure is not None:
                    raise CytonReaderError(failure)
                if on_idle is not None:
                    on_idle(time.monotonic())
                if not reader.is_alive():
                    report = dict(kind='unexpected_exit', exitcode=reader.exitcode)
                    if error_recv.poll(.1):
                        try:
                            report = error_recv.recv()
                        except EOFError:
                            pass
                    raise CytonReaderError(report)
                if not wait_for_data and time.monotonic()-last_yield >= timeout:
                    raise TimeoutError(f"No complete Cyton packet for {timeout:g} seconds")
    finally:
        stopped.set()
        reader.join(timeout=1)
        if reader.is_alive():
            reader.terminate()
            reader.join(timeout=1)
        error_recv.close()
        pending.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", default="/dev/ttyUSB0")
    parser.add_argument("--windows", type=int, default=0,
                        help="0 continues until Ctrl+C")
    parser.add_argument("--center-samples", type=int, default=25)
    parser.add_argument("--filter-batch-samples", type=int, choices=(1, 5, 10, 25), default=10,
                        help="continuous prefilter batch; 10 samples add at most 36ms at 250Hz after startup")
    parser.add_argument("--filter-backend", choices=("arm", "pl"), default="arm",
                        help="PL requires the integrated Overlay and kernel DMA owner; ARM is the default")
    parser.add_argument("--microvolts-per-count", type=float, default=DEFAULT_UV_PER_COUNT)
    parser.add_argument("--allow-clipping", action="store_true",
                        help="legacy option; clipping never makes a window valid")
    parser.add_argument("--stream-timeout", type=float, default=5.0)
    parser.add_argument('--wait-for-data', action='store_true',
                        help='live service waits through radio silence; serial faults still fail')
    parser.add_argument("--status-file", default="/tmp/guardianloop_status.json")
    parser.add_argument("--telemetry-file", default="/tmp/guardianloop_telemetry.json")
    parser.add_argument("--emotion-model", default=str(
        Path(__file__).with_name("gameemo_emotion_model.json")))
    parser.add_argument("--covariance-model", default=os.environ.get(
        "GL_COVARIANCE_MODEL", str(Path(__file__).with_name("gameemo_covariance_svm.npz"))),
                        help="six-channel 12-second candidate; legacy model is used if absent")
    parser.add_argument("--channel-map", default=os.environ.get(
        "GL_CHANNEL_MAP", ",".join(DEFAULT_CHANNEL_MAP)),
                        help="physical N1P..N8P locations, comma-separated and ordered")
    parser.add_argument("--fatigue-model", default=str(
        Path(__file__).with_name("cyton_fatigue_overlap4.json")),
                        help="portable four-channel fatigue candidate for the fixed cap")
    parser.add_argument("--esp32-url", default=os.environ.get("GL_ESP32_URL", ""),
                        help="optional ESP32 base URL, for example http://192.168.4.1")
    parser.add_argument('--mi-experimental-model', type=Path)
    parser.add_argument('--allow-experimental-mi', action='store_true')
    parser.add_argument('--mi-source', choices=('live', 'replay'), default='live')
    parser.add_argument('--mi-web-host', default='127.0.0.1')
    parser.add_argument('--mi-web-port', type=int, default=9104)
    parser.add_argument('--mi-audit-log', type=Path)
    parser.add_argument('--isolated-primary-worker', action='store_true',
                        help='private /dev/null ARM replay only; never a live deployment flag')
    parser.add_argument('--primary-worker-cpus', choices=('inherit', '0,1'), default='inherit')
    parser.add_argument('--isolated-reader-batch', action='store_true',
                        help='ten-packet IPC only inside the private primary-worker replay')
    parser.add_argument('--isolated-primary-checkpoint', action='store_true',
                        help='checkpoint rehearsal only in a fresh /dev/shm/gl-primary-recovery-* directory')
    parser.add_argument('--live-primary-worker', action='store_true',
                        help='pinned Cyton service only; asynchronous primary windows and ten-packet reader IPC')
    args = parser.parse_args()
    if args.isolated_primary_worker and (args.port != '/dev/null'
            or args.filter_backend != 'arm' or args.wait_for_data or args.esp32_url):
        parser.error('Primary worker is limited to isolated /dev/null ARM replay without ESP32')
    if args.primary_worker_cpus != 'inherit' and not args.isolated_primary_worker:
        parser.error('Primary worker CPU policy requires the isolated candidate')
    if args.isolated_reader_batch and not args.isolated_primary_worker:
        parser.error('Reader batching requires the isolated primary-worker candidate')
    if args.isolated_primary_checkpoint:
        recovery = Path(args.status_file).resolve().parent
        if (not args.isolated_primary_worker or recovery.parent != Path('/dev/shm')
                or not recovery.name.startswith('gl-primary-recovery-')
                or Path(args.telemetry_file).resolve().parent != recovery):
            parser.error('Checkpoint rehearsal requires the private worker and its tmpfs outputs')
    if args.allow_experimental_mi != bool(args.mi_experimental_model):
        parser.error('MI requires both --mi-experimental-model and --allow-experimental-mi')
    if args.windows < 0 or args.center_samples <= 0 or args.stream_timeout <= 0:
        raise SystemExit("Invalid argument range")
    if args.wait_for_data and (args.windows != 0 or args.mi_source != 'live'):
        parser.error('--wait-for-data is only for continuous live acquisition')
    if not math.isfinite(args.microvolts_per_count) or args.microvolts_per_count <= 0:
        raise SystemExit("--microvolts-per-count must be finite and positive")
    channel_map = tuple(item.strip().upper() for item in args.channel_map.split(","))
    if len(channel_map) != CHANNELS or len(set(channel_map)) != CHANNELS or any(not item for item in channel_map):
        raise SystemExit(f"--channel-map must contain exactly {CHANNELS} non-empty names")
    if args.live_primary_worker:
        validate_live_primary(args, channel_map)
    if args.filter_backend == "pl" and args.filter_batch_samples != 10:
        raise SystemExit("PL filter requires exactly 10 samples per DMA frame")

    print(f"CYTON_DIRECT_CONFIG: port={args.port} rate=250 channels=8 "
          f"uV_per_count={args.microvolts_per_count:.12f}", flush=True)
    fatigue_model_ready = channel_map == FATIGUE_MODEL_CHANNEL_MAP
    engine = GuardianLoopPynq() if fatigue_model_ready else None
    four_channel_fatigue = None
    if channel_map == DEFAULT_CHANNEL_MAP and Path(args.fatigue_model).is_file():
        four_channel_fatigue = FourChannelFatigue(args.fatigue_model)
        print("FATIGUE_MODEL_READY: fixed-cap T7,T8,O1,O2; Z15 ARM inference", flush=True)
    if engine is None and four_channel_fatigue is None:
        print("FATIGUE_MODEL_DISABLED: channel map mismatch; "
              f"actual={','.join(channel_map)} "
              f"expected={','.join(FATIGUE_MODEL_CHANNEL_MAP)}", flush=True)
    sqi_monitor = CytonSQIMonitor(calibration_windows=15, sample_rate_hz=250)
    emotion_disabled = None
    covariance_model = None
    covariance_stream = None
    if Path(args.covariance_model).is_file():
        try:
            covariance_model = CovarianceSVM(args.covariance_model)
            covariance_stream = CovarianceFeatureStream(channel_map,
                storage=os.environ.get('GL_COVARIANCE_STORAGE','deque'))
            print(f"COVARIANCE_MODEL_READY: {args.covariance_model}", flush=True)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            print(f"COVARIANCE_MODEL_DISABLED: {exc}", flush=True)
            covariance_model = None
            covariance_stream = None
    try:
        emotion_model = None if covariance_model is not None else GameemoEmotionRecognizer(args.emotion_model)
        if emotion_model is None:
            expected_channel_map = ()
        else:
            expected_channel_map = tuple(
                str(item).strip().upper() for item in emotion_model.model["channels"])
        if emotion_model is not None and not set(expected_channel_map).issubset(channel_map):
            emotion_disabled = {
                "valid": False,
                "state": "channel_map_mismatch",
                "actual_channel_map": list(channel_map),
                "expected_channel_map": list(expected_channel_map),
            }
            emotion_model = None
            print("EMOTION_MODEL_DISABLED: channel map mismatch; "
                  f"actual={','.join(channel_map)} expected={','.join(expected_channel_map)}",
                  flush=True)
        elif emotion_model is not None:
            print(f"EMOTION_MODEL_READY: {args.emotion_model} "
                  f"channels={','.join(channel_map)}", flush=True)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        emotion_model = None
        emotion_disabled = {
            "valid": False, "state": "model_unavailable", "detail": str(exc),
        }
        print(f"EMOTION_MODEL_DISABLED: {exc}", flush=True)
    try:
        eeg_filter = (KernelOwnedCausalFilter() if args.filter_backend == "pl"
                      else CausalEEGFilter(sample_rate_hz=250))
    except (OSError, RuntimeError) as exc:
        if args.filter_backend == "pl":
            publish_result({"valid": False, "state": "INVALID",
                            "reason": "PL_FILTER_UNAVAILABLE", "filter_backend": "pl",
                            "channel_map": list(channel_map)}, False,
                           args.status_file, args.esp32_url)
            print(f"PL_FILTER_ABORT: startup: {type(exc).__name__}: {exc}", flush=True)
        raise
    print(f"CYTON_FILTER_BACKEND: {args.filter_backend}", flush=True)
    try:
        fd = os.open(args.port, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
    except BaseException:
        if args.filter_backend == "pl":
            eeg_filter.close()
        raise
    prefilter_pending = []
    center_rows = []
    offsets = None
    previous_sequence = None
    windows = 0
    packets_seen = 0
    sequence_gaps = 0
    unresolved_gaps = 0
    malformed_bytes = 0
    clipped_rows = 0
    dropped_packets = 0
    telemetry_rows = deque(maxlen=625)
    raw_telemetry_rows = deque(maxlen=625)
    telemetry_divider = 0
    telemetry_sample_index = 0
    last_telemetry = 0.0
    calibration_ready = False
    calibration_session = None
    wear_session = WearSession(Path(args.status_file).parent)
    wear_id = wear_session.initialize()
    if (args.wait_for_data or args.isolated_primary_checkpoint) and four_channel_fatigue is not None:
        calibration_session = CalibrationSession(
            Path(args.status_file).with_name('calibration-session.json'),
            CalibrationSession.context_for(args.port, channel_map, args.microvolts_per_count,
                (args.fatigue_model, args.covariance_model, args.emotion_model), args.filter_backend))
        calibration_session.context['wear_id'] = wear_id
        try:
            restored = calibration_session.load(sqi_monitor, four_channel_fatigue)
            calibration_ready = four_channel_fatigue.mean is not None
            print('CALIBRATION_SESSION: ' + json.dumps(dict(restored=restored,
                fatigue_windows=len(four_channel_fatigue.baseline),
                sqi_channels=int(np.sum(sqi_monitor.calibrated_channels)))), flush=True)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            print('CALIBRATION_CHECKPOINT_REJECTED: ' + str(exc), flush=True)
    processor = PrimaryWindowProcessor(sqi_monitor, four_channel_fatigue,
        covariance_model, covariance_stream, emotion_model, emotion_disabled, engine,
        channel_map, args.microvolts_per_count, args.filter_backend, primary_windows, segmented_sqi)
    primary_worker = None
    if args.isolated_primary_worker or args.live_primary_worker:
        if four_channel_fatigue is None or engine is not None or channel_map != DEFAULT_CHANNEL_MAP:
            raise ValueError('Isolated worker requires the fixed-eight ARM fatigue engine')
        from async_primary import AsyncPrimaryWorker
        worker_options = dict(cpus={0, 1} if args.primary_worker_cpus == '0,1' else None)
        if calibration_session is not None:
            worker_options['calibration_session'] = calibration_session
        primary_worker = AsyncPrimaryWorker(processor, **worker_options)
        print('PRIMARY_WORKER_READY: ' + json.dumps(primary_worker.identity), flush=True)
    last_sqi = None
    last_raw_interference = None
    last_emotion = None
    shadow = None
    try:
        if os.environ.get('GL_SEED_EXECUTION','sync')=='async':
            from async_seed_candidate import AsyncSeedShadow
            shadow = AsyncSeedShadow(Path(__file__).with_name('seed_shadow_weights.npz'),channel_map,
                status_path=LIVE_PATH,source='live',page_policy_path=os.environ.get('GL_PAGE_POLICY_PATH'))
            print('SEED_CANDIDATE_READY: isolated bounded process; primary models unchanged',flush=True)
        else:
            shadow = SeedShadow(Path(__file__).with_name('seed_shadow_weights.npz'), channel_map)
    except (OSError, ValueError, KeyError) as exc:
        atomic_json(LIVE_PATH, {'state':'error','valid':False,'source':'live',
                              'updated_at':time.time(),'reason':str(exc)})
    recorder = TrialRecorder(channel_map, args.microvolts_per_count)
    ssvep = None
    try:
        ssvep = SSVEPReaderRuntime(Path(__file__).with_name('ssvep_causal_protocol.json'),
            Path(__file__).with_name('ssvep_candidate_sos.npy'), channel_map,
            decode_eeg_counts, args.microvolts_per_count, record_status_path=RECORDING_STATUS_PATH,
            reader_batch_samples=10 if args.live_primary_worker else 1)
    except (OSError, ValueError, KeyError) as exc:
        atomic_json(SSVEP_PATH, {'state':'error','valid':False,'source':'live',
                                'control_enabled':False,'updated_at':time.time(),'reason':str(exc)})
    telemetry_writer = TelemetryWriter()
    started_at = time.monotonic()
    queue_delay_max_ms = 0.0
    last_window_ms = None
    last_filter_ms = None
    max_filter_ms = 0.0
    last_received_at = None
    awaiting_resume = False
    primary_resets = 0
    stale_packets_discarded = 0
    resume_clean_packets = 0
    interruption_reason = None
    shutdown_reason = 'SERVICE_STOPPED_OR_STREAM_TIMEOUT'
    mi = None
    primary_worker_blocked = False
    last_primary_poll = 0.

    def invalidate_primary(reason):
        nonlocal awaiting_resume, last_emotion, interruption_reason, resume_clean_packets
        awaiting_resume = True
        resume_clean_packets = 0
        interruption_reason = reason
        last_emotion = {"valid":False, "state":"stream_interrupted", "reason":reason}
        if primary_worker is not None:
            primary_worker.invalidate()
        publish_result({"valid":False, "state":"INVALID", "reason":reason,
                        "window":windows, "emotion":last_emotion,
                        "calibration_current": calibration_progress(),
                        "calibration_retained": calibration_progress() > 0,
                        "filter_backend": args.filter_backend,
                        "channel_map":list(channel_map), **recording_counters()},
                       False, args.status_file, args.esp32_url)

    def on_idle(now):
        nonlocal resume_clean_packets
        # Stop acknowledgements and bounded raw-capture expiry also work without packets.
        recorder.poll(recording_counters())
        poll_wear_session()
        if mi is not None and mi.adapter is not None:
            mi.adapter.idle(now)
        if shadow is not None:
            shadow.idle(now)
        if last_received_at is not None and now - last_received_at > .5 and not awaiting_resume:
            invalidate_primary('STREAM_IDLE')
        if last_received_at is not None and now - last_received_at > .5:
            resume_clean_packets = 0
        poll_primary(now)

    def stream_configured():
        print('CYTON_EEG_CHANNELS_CONFIGURED: gain=24 bias=on srb2=on acknowledgements=8/8', flush=True)
        print('CYTON_STREAM_STARTED', flush=True)
        publish_result({'valid':False, 'state':'INVALID', 'reason':'STREAM_STARTING',
                        'calibration_current':calibration_progress(),
                        'calibration_retained':calibration_progress() > 0,
                        'emotion':{'valid':False, 'state':'collecting_12s'},
                        'channel_map':list(channel_map)}, False, args.status_file, args.esp32_url)

    def reconfigure_stream(reason):
        if not awaiting_resume:
            invalidate_primary(reason)

    def reset_primary_stream():
        nonlocal offsets, calibration_ready
        nonlocal last_sqi, last_raw_interference, last_telemetry, telemetry_divider
        nonlocal awaiting_resume, primary_resets, last_window_ms
        eeg_filter.reset()
        if primary_worker is None:
            processor.reset_stream()
        for buffer in (prefilter_pending, center_rows, telemetry_rows, raw_telemetry_rows):
            buffer.clear()
        offsets = None
        telemetry_divider = 0
        calibration_ready = (primary_worker.calibration_ready if primary_worker is not None
                             else processor.calibration_ready)
        last_sqi = last_raw_interference = last_window_ms = None
        last_telemetry = 0.
        awaiting_resume = False
        primary_resets += 1
        print('PRIMARY_STREAM_RESET: ' + json.dumps(dict(reason=interruption_reason,
            calibration_retained=True, fatigue_windows=calibration_progress(),
            sqi_channels=int(primary_worker.progress[2]) if primary_worker is not None else int(np.sum(sqi_monitor.calibrated_channels)), packets_seen=packets_seen,
            malformed_bytes=malformed_bytes, sequence_gaps=sequence_gaps)), flush=True)
    def stop_service(_signum, _frame):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, stop_service)

    def recording_counters():
        return {"packets_seen": packets_seen,
                "sequence_gaps": sequence_gaps,
                "unresolved_gaps": unresolved_gaps,
                "malformed_bytes": malformed_bytes,
                "dropped_packets": dropped_packets}

    def calibration_progress():
        return (primary_worker.calibration_progress if primary_worker is not None
                else processor.calibration_progress)

    def withdraw_worker_result(reason):
        nonlocal primary_worker_blocked, last_emotion
        last_emotion = dict(valid=False, state='processing_backlog', reason=reason)
        if primary_worker_blocked:
            return
        primary_worker_blocked = True
        publish_result(dict(valid=False, state='INVALID', reason=reason,
            window=windows, emotion=last_emotion, calibration_current=calibration_progress(),
            calibration_retained=calibration_progress()>0, filter_backend=args.filter_backend,
            channel_map=list(channel_map), **recording_counters()),
            False, args.status_file, args.esp32_url)

    def accept_primary(result, ready, age, elapsed_ms, received_at=None):
        nonlocal windows, clipped_rows, calibration_ready, last_sqi, last_emotion
        nonlocal last_raw_interference, last_window_ms, primary_worker_blocked
        windows = result['window']
        clipped_rows = result['clipped_rows']
        calibration_ready = ready
        last_sqi, last_emotion = result['sqi'], result['emotion']
        last_raw_interference = result['raw_interference']
        if calibration_session is not None and primary_worker is None:
            try:
                calibration_session.save(sqi_monitor, four_channel_fatigue)
            except (OSError, ValueError) as exc:
                print('CALIBRATION_CHECKPOINT_WRITE_FAILED: ' + str(exc), flush=True)
        recorder.record_window(result)
        print(f"CYTON_WINDOW_RESULT: {json.dumps(result, sort_keys=True)}", flush=True)
        if received_at is not None:
            # Logging and recording are part of publication latency, too.
            age = max(0., time.monotonic()-received_at)
            if age > MAX_PROCESSING_AGE_SECONDS:
                primary_worker.stats['publication_stale'] += 1
                withdraw_worker_result('PRIMARY_WORKER_RESULT_STALE')
                return
        primary_worker_blocked = False
        publish_result(result, calibration_ready, args.status_file, args.esp32_url,
                       input_age_seconds=age)
        last_window_ms = elapsed_ms

    def poll_primary(now):
        nonlocal last_primary_poll
        if primary_worker is None:
            return
        if 0 <= now-last_primary_poll < .02:
            return
        last_primary_poll = now
        if not awaiting_resume and primary_worker.lag(now) > MAX_PROCESSING_AGE_SECONDS:
            # Input still arrives in order: withdraw predictions, not samples
            # or the stateful calibration/filter history. Queue loss is separate.
            withdraw_worker_result('PRIMARY_WORKER_BACKLOG')
        for message in primary_worker.poll(now, MAX_PROCESSING_AGE_SECONDS):
            if not awaiting_resume:
                accept_primary(message['result'], message['calibrated'],
                               message['input_age_seconds'], message['compute_ms'], message['received_at'])

    def new_wearing(identifier):
        nonlocal sqi_monitor
        if calibration_session is None or four_channel_fatigue is None:
            raise ValueError('当前采集引擎不支持显式佩戴会话')
        # Remove the old checkpoint before accepting a new identity; a crash
        # must never restore another wearing's baseline.
        if primary_worker is not None:
            primary_worker.invalidate(new_wearing=True, wear_id=identifier)
        else:
            calibration_session.path.unlink(missing_ok=True)
            calibration_session.last_progress = None
            calibration_session.context['wear_id'] = identifier
        sqi_monitor = CytonSQIMonitor(calibration_windows=15, sample_rate_hz=250)
        processor.sqi_monitor = sqi_monitor
        four_channel_fatigue.reset()
        reset_primary_stream()
        invalidate_primary('EXPLICIT_NEW_WEARING')

    def poll_wear_session():
        wear_session.poll(new_wearing, recording=recorder.active is not None)
    try:
        if args.allow_experimental_mi:
            from mi_acquisition import MICandidateRuntime
            mi = MICandidateRuntime(args.mi_experimental_model, channel_map, source=args.mi_source,
                host=args.mi_web_host, port=args.mi_web_port, log_path=args.mi_audit_log,
                packet_decoder=decode_eeg_counts, microvolts_per_count=args.microvolts_per_count,
                reader_batch_samples=10 if args.live_primary_worker else 1,
                status_paths={'primary':args.status_file,
                              'seed':shadow.path if shadow is not None else LIVE_PATH,
                              'ssvep':ssvep.path if ssvep is not None else SSVEP_PATH})
        configure_serial(fd)
        for packet, malformed, received_at in configured_packets(fd, args.stream_timeout,
                on_idle=on_idle, on_configured=stream_configured, on_reconfigure=reconfigure_stream,
                packet_sink=mi.reader_sink if mi is not None else None,
                packet_sinks=(ssvep.reader_sink,) if ssvep is not None else (),
                **({'wait_for_data': True} if args.wait_for_data else {}),
                **({'reader_batch_samples': 10}
                   if args.isolated_reader_batch or args.live_primary_worker else {})):
            poll_wear_session()
            poll_primary(time.monotonic())
            queue_delay_ms = max(0.0, (time.monotonic() - received_at) * 1000.0)
            queue_delay_max_ms = max(queue_delay_max_ms, queue_delay_ms)
            if queue_delay_ms > MAX_PROCESSING_AGE_SECONDS * 1000 and not awaiting_resume:
                invalidate_primary('PROCESSING_BACKLOG')
            if last_received_at is not None and (received_at-last_received_at > .25 or received_at < last_received_at):
                resume_clean_packets = 0
                if not awaiting_resume:
                    invalidate_primary('STREAM_TIMING_GAP')
            if malformed and not awaiting_resume:
                invalidate_primary('MALFORMED_STREAM')
            last_received_at = received_at
            sequence = packet[1]
            counts = decode_eeg_counts(packet)
            if shadow is not None and queue_delay_ms <= MAX_PROCESSING_AGE_SECONDS * 1000:
                try:
                    shadow.packet(counts.astype(np.float64) * args.microvolts_per_count,
                                  sequence, bool(malformed), now=received_at, timing_verified=True)
                except (ValueError, FloatingPointError, np.linalg.LinAlgError) as exc:
                    shadow.disconnect('candidate_error')
                    shadow.publish({'state':'error','valid':False,'reason':str(exc)})
                    shadow = None
                    print('SEED_SHADOW_DISABLED: ' + str(exc), flush=True)
            delta = ((sequence - previous_sequence) & 0xFF) if previous_sequence is not None else 1
            gap = previous_sequence is not None and delta != 1
            previous_sequence = sequence
            packets_seen += 1
            malformed_bytes += malformed
            if gap:
                if not awaiting_resume:
                    invalidate_primary('SEQUENCE_GAP')
                sequence_gaps += 1
                # A backward/resync counter jump is not evidence of 100+ lost
                # radio packets. Count only short, clean forward gaps.
                if malformed == 0 and 1 < delta <= 32:
                    dropped_packets += delta - 1
                else:
                    unresolved_gaps += 1

            recorder.poll(recording_counters())
            try:
                recorder.append(counts, sequence, gap, malformed,
                                stream_index=packets_seen-1, received_at=received_at)
            except (OSError, ValueError) as exc:
                print('RAW_RECORDING_ERROR: ' + str(exc), flush=True)
                try:
                    recorder.close(recording_counters())
                except OSError as close_error:
                    print('RAW_RECORDING_CLOSE_ERROR: ' + str(close_error), flush=True)
                try:
                    recorder.publish('error', str(exc))
                except OSError as status_error:
                    print('RAW_RECORDING_STATUS_ERROR: ' + str(status_error), flush=True)

            if queue_delay_ms > MAX_PROCESSING_AGE_SECONDS * 1000:
                resume_clean_packets = 0
                stale_packets_discarded += 1
                if not awaiting_resume:
                    invalidate_primary('PROCESSING_BACKLOG')
                continue

            if awaiting_resume:
                # Preserve diagnostics/recording, but never feed a fault burst
                # into freshly reset filters or rebuild state on every bad frame.
                if malformed or gap:
                    resume_clean_packets = 0
                    continue
                resume_clean_packets += 1
                if resume_clean_packets < 125:
                    continue
                try:
                    reset_primary_stream()
                except (OSError, RuntimeError) as exc:
                    if args.filter_backend != "pl":
                        raise
                    shutdown_reason = "PL_FILTER_RESET_UNCERTAIN"
                    print(f"PL_FILTER_ABORT: reset: {type(exc).__name__}: {exc}", flush=True)
                    raise

            if offsets is None:
                if gap or malformed:
                    center_rows.clear()
                    continue
                center_rows.append(counts)
                if len(center_rows) < args.center_samples:
                    continue
                offsets = np.stack(center_rows).mean(axis=0)
                print("CYTON_CENTER_OFFSETS_COUNTS: " +
                      ", ".join(f"{value:.2f}" for value in offsets), flush=True)
                incoming = center_rows
                center_rows = []
            else:
                incoming = (counts,)

            prefilter_pending.extend((raw, bool(gap or malformed)) for raw in incoming)
            count = len(prefilter_pending) // args.filter_batch_samples * args.filter_batch_samples
            if not count:
                continue
            batch = prefilter_pending[:count]
            del prefilter_pending[:count]
            batch_uv = (np.asarray([item[0] for item in batch], dtype=np.float64) - offsets) * args.microvolts_per_count
            filter_started = time.monotonic()
            try:
                batch_filtered = eeg_filter.process(batch_uv)
            except (OSError, RuntimeError, OverflowError) as exc:
                if args.filter_backend != "pl":
                    raise
                shutdown_reason = "PL_FILTER_UNCERTAIN"
                print(f"PL_FILTER_ABORT: {type(exc).__name__}: {exc}", flush=True)
                raise
            last_filter_ms = (time.monotonic() - filter_started) * 1000.0
            max_filter_ms = max(max_filter_ms, last_filter_ms)
            if primary_worker is not None:
                accepted = primary_worker.submit([item[0] for item in batch], batch_filtered,
                    [item[1] for item in batch], recording_counters(), received_at)
                if not accepted:
                    invalidate_primary(primary_worker.last_submit_rejection)
                    continue
            for (raw, sample_bad), raw_uv, filtered_uv in zip(batch, batch_uv, batch_filtered):
                window_started = time.monotonic()
                result = (processor.append(raw, filtered_uv, sample_bad, recording_counters())
                          if primary_worker is None else None)
                telemetry_divider += 1
                if offsets is not None and telemetry_divider >= 2:
                    telemetry_divider = 0
                    telemetry_rows.append(filtered_uv)
                    raw_telemetry_rows.append(raw_uv)
                    telemetry_sample_index += 1
                now = time.monotonic()
                if telemetry_rows and now - last_telemetry >= 0.5:
                    telemetry_writer.submit(telemetry_rows, raw_telemetry_rows,
                                      telemetry_sample_index, args.telemetry_file, packets_seen,
                                      dropped_packets, sequence_gaps, unresolved_gaps, malformed_bytes,
                                      clipped_rows, last_sqi, last_emotion,
                                      diagnostics={"uptime_seconds": now - started_at,
                                                   "input_age_at_snapshot_ms": max(0.0, (now - received_at) * 1000.0),
                                                   "reader_queue_delay_ms": queue_delay_ms,
                                                   "reader_queue_delay_max_ms": queue_delay_max_ms,
                                                   "last_window_compute_ms": last_window_ms,
                                                   "filter_backend": args.filter_backend,
                                                   "last_filter_compute_ms": last_filter_ms,
                                                   "max_filter_compute_ms": max_filter_ms,
                                                   "primary_stream_resets": primary_resets,
                                                   "stale_packets_discarded": stale_packets_discarded,
                                                   "last_interruption_reason": interruption_reason,
                                                   "filter_batch_samples": args.filter_batch_samples})
                    last_telemetry = now

                if result is not None:
                    accept_primary(result, processor.calibration_ready,
                        max(0., time.monotonic()-received_at),
                        (time.monotonic()-window_started)*1000.)
                if args.windows and windows >= args.windows:
                    break
            if args.windows and windows >= args.windows:
                break
    except KeyboardInterrupt:
        print("STOPPED_BY_USER", flush=True)
    except CytonReaderError as exc:
        shutdown_reason = 'READER_' + exc.report['kind'].upper()
        print(str(exc), flush=True)
        raise
    except TimeoutError as exc:
        shutdown_reason = 'SERIAL_TIMEOUT'
        print('CYTON_READER_TIMEOUT: ' + str(exc), flush=True)
        raise
    finally:
        invalidate_primary(shutdown_reason)
        if primary_worker is not None:
            primary_worker.close()
            if calibration_session is not None:
                primary_worker.stats['checkpoint_write_failures'] = primary_worker.checkpoint_write_failures
            print('PRIMARY_WORKER_STATS: ' + json.dumps(primary_worker.stats), flush=True)
        telemetry_writer.close()
        print(f"TELEMETRY_DISPLAY_SKIPPED: snapshots={telemetry_writer.skipped} raw_samples_not_dropped", flush=True)
        if prefilter_pending:
            print(f"FILTER_TAIL_DISCARDED: samples={len(prefilter_pending)} incomplete_batch_only", flush=True)
        if shadow is not None:
            shadow.disconnect('service_stopped_or_stream_timeout')
        if ssvep is not None:
            ssvep.close()
        try:
            try:
                recorder.close(recording_counters())
            finally:
                write_command(fd, b"s")
                time.sleep(0.1)
        finally:
            try:
                if args.filter_backend == "pl":
                    eeg_filter.close()
            finally:
                try:
                    os.close(fd)
                finally:
                    if mi is not None:
                        mi.close()
    print(f"CYTON_DIRECT_COMPLETE: windows={windows} packets={packets_seen} "
          f"dropped_packets={dropped_packets} sequence_gaps={sequence_gaps} "
          f"unresolved_gaps={unresolved_gaps} "
          f"malformed_bytes={malformed_bytes} "
          f"clipped_rows={clipped_rows}", flush=True)


if __name__ == "__main__":
    main()

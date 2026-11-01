#!/usr/bin/env python3
"""Run GuardianLoop directly from an OpenBCI Cyton USB dongle on the Z15."""

import argparse
import errno
import json
import math
import multiprocessing
import os
import queue
import select
import signal
import termios
import time
import urllib.error
import urllib.request
from collections import deque
from pathlib import Path

import numpy as np

from guardianloop_pynq import CHANNELS, WINDOW_SAMPLES, GuardianLoopPynq
from cyton_sqi import CausalEEGFilter, CytonSQIMonitor, GameemoEmotionRecognizer, channel_sqi
from pl_causal_filter import KernelOwnedCausalFilter
from cyton_covariance import CovarianceFeatureStream, CovarianceSVM, WINDOW_SAMPLES as COVARIANCE_SAMPLES
from cyton_trial_recorder import TrialRecorder
from cyton_fatigue import FourChannelFatigue, PHYSICAL_INDICES
from seed_shadow import SeedShadow, LIVE_PATH
from ssvep_shadow import LIVE_PATH as SSVEP_PATH
from ssvep_acquisition import SSVEPReaderRuntime
from cyton_reader_sink import decode_eeg_counts
from cyton_trial_recorder import atomic_json, STATUS_PATH as RECORDING_STATUS_PATH


PACKET_BYTES = 33
START_BYTE = 0xA0
DEFAULT_UV_PER_COUNT = 4_500_000.0 / 24.0 / (2**23 - 1)
DEFAULT_CHANNEL_MAP = ("F3", "F4", "C3", "C4", "T7", "T8", "O1", "O2")
FATIGUE_MODEL_CHANNEL_MAP = ("FT7", "FT8", "CP1", "CP2", "P1", "P2", "O1", "O2")


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
                      clipped_rows, sqi=None, emotion=None, snapshot_time=None, diagnostics=None):
    if not path or len(samples) == 0:
        return
    total = packets_seen + dropped_packets
    payload = {
        "source": "cyton_usb",
        "real": True,
        "updated_at": time.time() if snapshot_time is None else snapshot_time,
        "sample_rate_hz": 125,
        "channels": CHANNELS,
        "samples": np.round(np.asarray(samples), 3).tolist(),
        "raw_samples": np.round(np.asarray(raw_samples), 3).tolist(),
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
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, separators=(",", ":"), allow_nan=False),
                         encoding="utf-8")
    temporary.replace(destination)


def _telemetry_worker(pending):
    while True:
        args = pending.get()
        if args is None:
            return
        publish_telemetry(*args)


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
        snapshot = (np.asarray(samples).copy(), np.asarray(raw_samples).copy()) + args + (time.time(), info)
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
    os.write(fd, command)
    termios.tcdrain(fd)


def configure_eeg_channels(fd):
    """Put every Cyton channel in the referential EEG configuration.

    OpenBCI GUI applies these settings when it connects, but a direct serial
    client cannot rely on whatever volatile state a previous program left in
    the board.  The seven channel fields are power=on, gain=24, input=normal,
    include-in-bias=yes, SRB2=on, and SRB1=off.
    """
    write_command(fd, b"c")  # Explicitly select the eight-channel board mode.
    settings = b"".join(
        f"x{channel}060110X".encode("ascii")
        for channel in range(1, CHANNELS + 1)
    )
    write_command(fd, settings)


class CytonReaderError(RuntimeError):
    """Terminal serial-reader failure with no raw EEG in the diagnostic."""

    def __init__(self, report):
        self.report = report
        super().__init__('CYTON_READER_FAILURE: ' + json.dumps(report, sort_keys=True))


def packets(fd, timeout, with_timing=False, on_idle=None, *, queue_capacity=8192,
            read_chunk=os.read, packet_sink=None, packet_sinks=(), wait_for_data=False):
    if queue_capacity < 1:
        raise ValueError('queue_capacity must be positive')
    context = multiprocessing.get_context("fork")
    pending = context.Queue(maxsize=queue_capacity)
    stopped = context.Event()
    error_recv, error_send = context.Pipe(duplex=False)

    def read_serial():
        error_recv.close()
        buffer = bytearray()
        malformed = 0
        locked = False
        reads = bytes_read = packets_queued = empty_reads = 0
        try:
            while not stopped.is_set():
                readable, _, _ = select.select([fd], [], [], 0.2)
                if not readable:
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
                        malformed += len(buffer)
                        buffer.clear()
                        break
                    if start:
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
                    for sink in packet_sinks:
                        sink.offer(packet, malformed, received_at)
                    if packet_sink is not None:
                        packet_sink.offer(packet, malformed, received_at)
                    pending.put_nowait((packet, malformed, received_at))
                    packets_queued += 1
                    del buffer[:PACKET_BYTES]
                    malformed = 0
        except Exception as exc:
            kind = ('queue_full' if isinstance(exc, queue.Full) else
                    'serial_eof' if isinstance(exc, EOFError) else
                    'serial_io_error' if isinstance(exc, OSError) else 'reader_exception')
            report = dict(kind=kind, errno=getattr(exc, 'errno', None),
                          exception=type(exc).__name__, reads=reads,
                          bytes_read=bytes_read, packets_queued=packets_queued,
                          malformed_pending=malformed, empty_reads=empty_reads)
            try:
                error_send.send(report)
            except (BrokenPipeError, OSError):
                pass
        finally:
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
    try:
        while True:
            try:
                item = pending.get(timeout=min(timeout, .25))
                last_yield = time.monotonic()
                yield item if with_timing else item[:2]
            except queue.Empty:
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
    args = parser.parse_args()
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
    rows = deque(maxlen=WINDOW_SAMPLES)
    filtered_rows = deque(maxlen=WINDOW_SAMPLES)
    bad_rows = deque(maxlen=WINDOW_SAMPLES)
    covariance_bad_rows = deque(maxlen=COVARIANCE_SAMPLES)
    covariance_pending = []
    fatigue_pending = []
    prefilter_pending = []
    fatigue_new_samples = 0
    last_fatigue_result = None
    center_rows = []
    offsets = None
    previous_sequence = None
    new_samples = 0
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
            decode_eeg_counts, args.microvolts_per_count, record_status_path=RECORDING_STATUS_PATH)
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
    last_stream_probe = started_at
    primary_resets = 0
    shutdown_reason = 'SERVICE_STOPPED_OR_STREAM_TIMEOUT'
    mi = None

    def invalidate_primary(reason):
        nonlocal awaiting_resume, last_emotion, last_fatigue_result
        awaiting_resume = True
        last_emotion = {"valid":False, "state":"stream_interrupted", "reason":reason}
        last_fatigue_result = None
        publish_result({"valid":False, "state":"INVALID", "reason":reason,
                        "window":windows, "emotion":last_emotion,
                        "filter_backend": args.filter_backend,
                        "channel_map":list(channel_map), **recording_counters()},
                       False, args.status_file, args.esp32_url)

    def on_idle(now):
        nonlocal last_stream_probe
        # Stop acknowledgements and bounded raw-capture expiry also work without packets.
        recorder.poll(recording_counters())
        if mi is not None and mi.adapter is not None:
            mi.adapter.idle(now)
        if shadow is not None:
            shadow.idle(now)
        if last_received_at is not None and now - last_received_at > .5 and not awaiting_resume:
            invalidate_primary('STREAM_IDLE')
        if (args.wait_for_data and now - last_stream_probe >= max(5., args.stream_timeout)
                and (last_received_at is None or now - last_received_at >= args.stream_timeout)):
            if not awaiting_resume:
                invalidate_primary('WAITING_FOR_CYTON')
            # A board powered on after the initial 'b' needs a new start command.
            configure_eeg_channels(fd)
            write_command(fd, b'b')
            last_stream_probe = now
            print('CYTON_WAITING: no complete packets; configuration/start retried', flush=True)

    def reset_primary_stream():
        nonlocal eeg_filter, sqi_monitor, covariance_stream, four_channel_fatigue
        nonlocal offsets, new_samples, fatigue_new_samples, calibration_ready
        nonlocal last_sqi, last_raw_interference, last_telemetry, telemetry_divider
        nonlocal awaiting_resume, primary_resets, last_window_ms
        if args.filter_backend == "pl":
            eeg_filter.reset()
        else:
            eeg_filter = CausalEEGFilter(sample_rate_hz=250)
        sqi_monitor = CytonSQIMonitor(calibration_windows=15, sample_rate_hz=250)
        if covariance_stream is not None:
            covariance_stream = CovarianceFeatureStream(channel_map,
                storage=os.environ.get('GL_COVARIANCE_STORAGE','deque'))
        if four_channel_fatigue is not None:
            four_channel_fatigue = FourChannelFatigue(args.fatigue_model)
        for buffer in (rows, filtered_rows, bad_rows, covariance_bad_rows, covariance_pending,
                       fatigue_pending, prefilter_pending, center_rows, telemetry_rows, raw_telemetry_rows):
            buffer.clear()
        offsets = None
        new_samples = fatigue_new_samples = telemetry_divider = 0
        calibration_ready = False
        last_sqi = last_raw_interference = last_window_ms = None
        last_telemetry = 0.
        awaiting_resume = False
        primary_resets += 1
        print('PRIMARY_STREAM_RESET: fresh filters, windows and calibration; SEED policy remains separate',flush=True)
    def stop_service(_signum, _frame):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, stop_service)

    def recording_counters():
        return {"packets_seen": packets_seen,
                "sequence_gaps": sequence_gaps,
                "unresolved_gaps": unresolved_gaps,
                "malformed_bytes": malformed_bytes,
                "dropped_packets": dropped_packets}
    try:
        if args.allow_experimental_mi:
            from mi_acquisition import MICandidateRuntime
            mi = MICandidateRuntime(args.mi_experimental_model, channel_map, source=args.mi_source,
                host=args.mi_web_host, port=args.mi_web_port, log_path=args.mi_audit_log,
                packet_decoder=decode_eeg_counts, microvolts_per_count=args.microvolts_per_count,
                status_paths={'primary':args.status_file,
                              'seed':shadow.path if shadow is not None else LIVE_PATH,
                              'ssvep':ssvep.path if ssvep is not None else SSVEP_PATH})
        configure_serial(fd)
        write_command(fd, b"s")
        time.sleep(0.25)
        configure_eeg_channels(fd)
        time.sleep(0.5)
        termios.tcflush(fd, termios.TCIFLUSH)
        print("CYTON_EEG_CHANNELS_CONFIGURED: gain=24 bias=on srb2=on", flush=True)
        write_command(fd, b"b")
        print("CYTON_STREAM_STARTED", flush=True)
        last_stream_probe = time.monotonic()
        publish_result({"valid":False, "state":"INVALID", "reason":"STREAM_STARTING",
                        "emotion":{"valid":False, "state":"collecting_12s"},
                        "channel_map":list(channel_map)}, False, args.status_file, args.esp32_url)

        for packet, malformed, received_at in packets(fd, args.stream_timeout, with_timing=True,
                on_idle=on_idle, packet_sink=mi.reader_sink if mi is not None else None,
                packet_sinks=(ssvep.reader_sink,) if ssvep is not None else (),
                **({'wait_for_data': True} if args.wait_for_data else {})):
            queue_delay_ms = max(0.0, (time.monotonic() - received_at) * 1000.0)
            queue_delay_max_ms = max(queue_delay_max_ms, queue_delay_ms)
            if last_received_at is not None and (received_at-last_received_at > .25 or received_at < last_received_at):
                if not awaiting_resume:
                    invalidate_primary('STREAM_TIMING_GAP')
            if malformed and not awaiting_resume:
                invalidate_primary('MALFORMED_STREAM')
            if awaiting_resume:
                try:
                    reset_primary_stream()
                except (OSError, RuntimeError) as exc:
                    if args.filter_backend != "pl":
                        raise
                    shutdown_reason = "PL_FILTER_RESET_UNCERTAIN"
                    print(f"PL_FILTER_ABORT: reset: {type(exc).__name__}: {exc}", flush=True)
                    raise
            last_received_at = received_at
            sequence = packet[1]
            counts = decode_eeg_counts(packet)
            if shadow is not None:
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
            for (raw, sample_bad), raw_uv, filtered_uv in zip(batch, batch_uv, batch_filtered):
                rows.append(raw.copy())
                filtered_rows.append(filtered_uv)
                if four_channel_fatigue is not None:
                    fatigue_pending.append(filtered_uv)
                    fatigue_new_samples += 1
                    if len(fatigue_pending) == 125:
                        four_channel_fatigue.append(np.asarray(fatigue_pending))
                        fatigue_pending.clear()
                bad_rows.append(sample_bad)
                if covariance_stream is not None:
                    covariance_pending.append(filtered_uv)
                    if len(covariance_pending) == 125:
                        covariance_stream.append(np.asarray(covariance_pending))
                        covariance_pending.clear()
                    covariance_bad_rows.append(sample_bad)
                new_samples += 1
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
                                                   "filter_batch_samples": args.filter_batch_samples})
                    last_telemetry = now

                hop = 500 if calibration_ready else WINDOW_SAMPLES
                if len(rows) < WINDOW_SAMPLES or new_samples < hop:
                    continue
                window_started = time.monotonic()
                window_counts = np.stack(rows).astype(np.float64)
                window_offsets = window_counts.mean(axis=0)
                raw_window_uv = (window_counts - window_offsets) * args.microvolts_per_count
                filtered_window_uv = np.stack(filtered_rows)
                window_uv = filtered_window_uv - filtered_window_uv.mean(axis=0)
                segment_count = WINDOW_SAMPLES // sqi_monitor.segment_samples
                raw_segments = raw_window_uv.reshape(
                    segment_count, sqi_monitor.segment_samples, CHANNELS)
                raw_descriptors = np.stack([channel_sqi(segment) for segment in raw_segments])
                last_raw_interference = {
                    "mains_ratio": np.max(raw_descriptors[:, :, 4], axis=0).round(6).tolist(),
                    "p99_abs_uv": np.max(raw_descriptors[:, :, 1], axis=0).round(3).tolist(),
                    "above_transport_ratio": np.mean(
                        np.abs(raw_window_uv) > 327.67, axis=0).round(6).tolist(),
                    "adc_near_rail_ratio": np.mean(
                        np.abs(window_counts) >= 0.95 * (2**23 - 1), axis=0).round(6).tolist(),
                }
                units = np.rint(window_uv * 100.0)
                in_range = np.isfinite(units) & (units >= -32768) & (units <= 32767)
                outside_rows = ~np.all(in_range, axis=1)
                channel_transport_ok = np.all(in_range, axis=0) & (not any(bad_rows))
                clipped_now = int(np.count_nonzero(outside_rows))
                clipped_rows += clipped_now
                safe_units = np.where(np.isfinite(units), units, 0)
                window_i16 = np.clip(safe_units, -32768, 32767).astype(np.int16)
                transport_ok = not any(bad_rows) and clipped_now == 0
                last_sqi = sqi_monitor.process(window_uv, transport_ok=channel_transport_ok)
                if covariance_model is not None:
                    try:
                        indexes = covariance_stream.indexes
                        quality = [last_sqi["channels"][i]["quality"]
                                   if last_sqi["channels"][i]["calibrated"] else 0.0
                                   for i in indexes]
                        if not covariance_stream.ready:
                            last_emotion = covariance_model.predict(covariance_stream, quality)
                        elif any(covariance_bad_rows):
                            last_emotion = {"valid": False, "state": "packet_gap_12s"}
                        else:
                            last_emotion = covariance_model.predict(covariance_stream, quality)
                        last_emotion["channel_map"] = list(covariance_model.metadata["channels"])
                        if sum(last_sqi["channels"][i]["calibrated"] for i in indexes) < 6:
                            last_emotion["valid"] = False
                            last_emotion["state"] = "sqi_calibrating"
                    except Exception as exc:
                        last_emotion = {"valid": False, "state": "error",
                                        "reason": type(exc).__name__, "detail": str(exc)}
                elif emotion_model is not None:
                    try:
                        last_emotion = emotion_model.predict(
                            window_uv,
                            [c["quality"] if c["calibrated"] else 0.0 for c in last_sqi["channels"]],
                            source_rate_hz=250, source_channel_map=channel_map)
                        last_emotion["channel_map"] = emotion_model.model["channels"]
                        model_indexes = emotion_model.channel_indices(channel_map)
                        if sum(last_sqi["channels"][i]["calibrated"] for i in model_indexes) < emotion_model.minimum_usable:
                            last_emotion["valid"] = False
                            last_emotion["state"] = "sqi_calibrating"
                    except Exception as exc:
                        last_emotion = {
                            "valid": False, "state": "error",
                            "reason": type(exc).__name__, "detail": str(exc),
                        }
                else:
                    last_emotion = dict(emotion_disabled or {
                        "valid": False, "state": "model_unavailable",
                    })
                if four_channel_fatigue is not None:
                    required = [last_sqi["channels"][i] for i in PHYSICAL_INDICES]
                    required_quality_ok = all(item["quality"] >= 0.5 for item in required)
                    required_transport_ok = bool(np.all(channel_transport_ok[list(PHYSICAL_INDICES)]))
                    if fatigue_new_samples >= WINDOW_SAMPLES:
                        if fatigue_pending:
                            four_channel_fatigue.append(np.asarray(fatigue_pending))
                            fatigue_pending.clear()
                        last_fatigue_result = four_channel_fatigue.process_window(
                            required_quality_ok, required_transport_ok)
                        fatigue_new_samples = 0
                    result = dict(last_fatigue_result or {
                        "valid": False, "state": "INVALID", "reason": "FEATURE_WARMUP",
                        "calibration_current": 0, "calibration_total": 15,
                    })
                    result["last_inference_window"] = result.get("window", 0)
                    result["window"] = windows + 1
                    result["window_hop_seconds"] = 8
                    result["algorithm_version"] = "seedvig-cyton-overlap4-arm-v1"
                    if result.get("state") in ("NORMAL", "MILD", "SEVERE"):
                        if not required_quality_ok or not required_transport_ok:
                            result.update(valid=False, state="INVALID",
                                          reason=("TRANSPORT" if not required_transport_ok
                                                  else "REQUIRED_CHANNEL_QUALITY"))
                        elif not all(item["calibrated"] for item in required):
                            result.update(valid=False, state="INVALID",
                                          reason="REQUIRED_CHANNEL_SQI_CALIBRATING")
                elif engine is None:
                    result = {
                        "window": windows + 1,
                        "valid": False,
                        "state": "INVALID",
                        "reason": "CHANNEL_MAP_MISMATCH",
                        "detail": "Fatigue model requires " + ",".join(FATIGUE_MODEL_CHANNEL_MAP),
                        "calibration_current": last_sqi["calibration_current"],
                        "calibration_total": last_sqi["calibration_total"],
                    }
                else:
                    try:
                        result = engine.process_window(window_i16, transport_ok=transport_ok)
                    except RuntimeError as exc:
                        if not str(exc).startswith("PL DE invalid result:"):
                            raise
                        result = {
                            "window": engine.window_index,
                            "valid": False,
                            "state": "INVALID",
                            "reason": "SIGNAL_SATURATION",
                            "detail": str(exc),
                            "calibration_current": len(engine.baseline),
                            "calibration_total": 15,
                        }
                windows += 1
                new_samples = 0
                calibration_ready = bool(result.get("calibration_ready")) or calibration_ready
                result.update(source="cyton_usb", packets_seen=packets_seen,
                              filter_backend=args.filter_backend,
                              dropped_packets=dropped_packets,
                              sequence_gaps=sequence_gaps, unresolved_gaps=unresolved_gaps,
                              malformed_bytes=malformed_bytes,
                              clipped_rows=clipped_rows, sqi=last_sqi,
                              raw_interference=last_raw_interference,
                              emotion=last_emotion,
                              channel_map=list(channel_map),
                              signal_quality=last_sqi["state"])
                recorder.record_window(result)
                print(f"CYTON_WINDOW_RESULT: {json.dumps(result, sort_keys=True)}", flush=True)
                publish_result(result, calibration_ready, args.status_file, args.esp32_url,
                               input_age_seconds=max(0., time.monotonic()-received_at))
                last_window_ms = (time.monotonic() - window_started) * 1000.0
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

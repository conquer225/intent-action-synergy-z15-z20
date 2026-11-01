"""Board-local, loss-auditable raw Cyton trial recording."""

import json
import math
import os
import struct
import time
import threading
from contextlib import contextmanager
from pathlib import Path


CONTROL_PATH = Path("/home/xilinx/.guardianloop_record_command.json")
STATUS_PATH = Path("/run/guardianloop/recording_status.json")
RECORD_ROOT = Path("/home/xilinx/jupyter_notebooks/guardianloop_pynq/recordings")
CONDITIONS = ("boring", "calm", "horror", "funny")
MAX_SECONDS = 600
_command_lock = threading.Lock()


@contextmanager
def recording_command_lock(path):
    """Serialize the public web and acquisition-owned recording controllers."""
    with _command_lock:
        if os.name == 'nt':
            # Windows runs the single-process no-device tests, not board services.
            yield
        else:
            import fcntl
            lock_path = Path(path).with_suffix('.lock')
            with lock_path.open('a') as stream:
                fcntl.flock(stream, fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    fcntl.flock(stream, fcntl.LOCK_UN)


def atomic_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    temporary.replace(path)


def read_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


class TrialRecorder:
    def __init__(self, channel_map, microvolts_per_count,
                 control_path=CONTROL_PATH, status_path=STATUS_PATH,
                 record_root=RECORD_ROOT):
        self.control_path = Path(control_path)
        self.status_path = Path(status_path)
        self.record_root = Path(record_root)
        self.channel_map = list(channel_map)
        self.microvolts_per_count = float(microvolts_per_count)
        self.last_command = read_json(self.control_path).get("id")
        self.last_poll = 0.0
        self.last_status = 0.0
        self.active = None
        self.publish("idle")

    def publish(self, state, detail=None):
        payload = {
            "state": state, "updated_at": time.time(),
            "last_command": self.last_command,
            "trial_id": self.active["trial_id"] if self.active else None,
            "condition": self.active["condition"] if self.active else None,
            "phase": self.active["metadata"]["phase"] if self.active else None,
            "task": self.active["metadata"]["task"] if self.active else None,
            "updated_monotonic": time.monotonic(),
            "samples": self.active["samples"] if self.active else 0,
            "elapsed_seconds": round(time.monotonic() - self.active["started_mono"], 1)
            if self.active else 0,
            "path": str(self.active["directory"]) if self.active else None,
        }
        if detail is not None:
            payload["detail"] = detail
        atomic_json(self.status_path, payload)
        self.last_status = time.monotonic()

    def poll(self, counters):
        now = time.monotonic()
        if now - self.last_poll < 0.2:
            return
        self.last_poll = now
        command = read_json(self.control_path)
        command_id = command.get("id")
        if command_id and command_id != self.last_command:
            self.last_command = command_id
            action = command.get("action")
            if action == "start" and self.active is None:
                try:
                    self.start(command, counters)
                except (OSError, ValueError) as exc:
                    self.publish("error", str(exc))
            elif action == "stop" and self.active is not None:
                if command.get("trial_id") == self.active["trial_id"]:
                    self.finish("complete", counters, command.get("self_report"),
                                command.get("browser_time_ms"))
                else:
                    self.publish("error", "trial ID does not match the active recording")
            else:
                self.publish("error", "invalid action or trial state")
        if self.active:
            if now - self.active["started_mono"] >= self.active['max_seconds']:
                self.finish("duration_limit", counters)
            elif now - self.last_status >= 1:
                self.publish("recording")

    def start(self, command, counters):
        trial_id = command.get("trial_id", "")
        if (not isinstance(trial_id, str) or len(trial_id) != 16
                or any(ch not in "0123456789abcdef" for ch in trial_id)):
            raise ValueError("invalid trial ID")
        condition = command.get("condition")
        task = command.get("task", "emotion")
        if task not in ("emotion", "ssvep"):
            raise ValueError("unknown recording task")
        if ((task == "emotion" and condition not in CONDITIONS)
                or (task == "ssvep" and (condition not in ("ssvep_cued_diagnostic", "ssvep_free_diagnostic", "ssvep_hdmi_diagnostic")
                    or command.get("phase") != "ssvep_diagnostic"))):
            raise ValueError("unknown condition")
        max_seconds = command.get('max_seconds', MAX_SECONDS) if task == 'ssvep' else MAX_SECONDS
        if type(max_seconds) is not int or not 1 <= max_seconds <= MAX_SECONDS:
            raise ValueError('invalid recording duration limit')
        directory = self.record_root / trial_id
        directory.mkdir(parents=True, exist_ok=False, mode=0o750)
        if hasattr(os, "chown"):
            import grp
            os.chown(directory, -1, grp.getgrnam("xilinx").gr_gid)
        raw_file = (directory / "samples_i32le.bin").open("wb")
        sequence_file = (directory / "sequence_u8.bin").open("wb")
        flags_file = (directory / "flags_u8.bin").open("wb")
        windows_file = (directory / "window_results.jsonl").open("w", encoding="utf-8")
        alignment_files = {}
        if task == "ssvep":
            alignment_files = {
                "stream_index_u64le.bin": (directory / "stream_index_u64le.bin").open("wb"),
                "arrival_mono_f64le.bin": (directory / "arrival_mono_f64le.bin").open("wb"),
            }
        metadata = {
            "format_version": 1, "trial_id": trial_id, "state": "recording",
            "task": task,
            "max_seconds": max_seconds,
            "condition_requested": condition,
            "phase": command.get("phase"),
            "participant_id": command.get("participant_id"),
            "stimulus_note": command.get("stimulus_note", ""),
            "channel_map": self.channel_map, "sample_rate_hz": 250,
            "microvolts_per_count": self.microvolts_per_count,
            "raw_format": "little-endian signed int32; consecutive 8-channel rows, N1P..N8P",
            "sequence_format": "one Cyton packet counter byte per row",
            "flags_format": "bit 0: sequence discontinuity; bit 1: malformed bytes before packet",
            "board_started_at": time.time(),
            "browser_started_at_ms": command.get("browser_time_ms"),
            "board_clock_verified": False,
            "start_counters": dict(counters),
            "label_provenance": ("browser cue is a requested target, not a verified neural response"
                                 if task == "ssvep" else
                                 "condition requested before trial; self-report entered after trial"),
        }
        if task == "ssvep":
            metadata.update(
                board_started_monotonic=time.monotonic(),
                board_boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
                    if Path('/proc/sys/kernel/random/boot_id').exists() else 'unavailable',
                stream_index_format="one little-endian uint64 zero-based service packet index per row",
                arrival_time_format="one little-endian float64 CLOCK_MONOTONIC USB receive timestamp per row",
                alignment_limitation="USB receive timestamps are not ADC or optical onset measurements",
                optical_onset_measured=False,
                cue_log_path=command.get('cue_log_path'),
                protocol=command.get('protocol'),
                protocol_digest=command.get('protocol_digest'),
                stream_first_index=counters['packets_seen']-1)
        self.active = {
            "trial_id": trial_id, "condition": condition,
            "max_seconds": max_seconds,
            "directory": directory, "started_mono": time.monotonic(),
            "raw_file": raw_file, "sequence_file": sequence_file,
            "flags_file": flags_file, "windows_file": windows_file,
            "buffer_raw": bytearray(), "buffer_seq": bytearray(),
            "buffer_flags": bytearray(), "samples": 0, "metadata": metadata,
            "alignment_files": alignment_files,
            "alignment_buffers": {name: bytearray() for name in alignment_files},
        }
        atomic_json(directory / "metadata.json", metadata)
        self.publish("recording")

    def append(self, counts, sequence, gap, malformed, *, stream_index=None, received_at=None):
        if self.active is None:
            return
        trial = self.active
        if trial["alignment_files"]:
            if (type(stream_index) is not int or stream_index < 0
                    or type(received_at) not in (int, float)
                    or not math.isfinite(received_at) or received_at < 0):
                raise ValueError("SSVEP raw recording requires a packet index and receive timestamp")
            trial['alignment_buffers']['stream_index_u64le.bin'].extend(struct.pack('<Q', stream_index))
            trial['alignment_buffers']['arrival_mono_f64le.bin'].extend(struct.pack('<d', received_at))
        trial["buffer_raw"].extend(struct.pack("<8i", *(int(item) for item in counts)))
        trial["buffer_seq"].append(sequence)
        trial["buffer_flags"].append(int(bool(gap)) | (2 if malformed else 0))
        trial["samples"] += 1
        if len(trial["buffer_seq"]) >= 250:
            self.flush()

    def flush(self):
        trial = self.active
        if trial is None or not trial["buffer_seq"]:
            return
        for name, key in (("raw_file", "buffer_raw"),
                          ("sequence_file", "buffer_seq"),
                          ("flags_file", "buffer_flags")):
            trial[name].write(trial[key])
            trial[name].flush()
            trial[key].clear()
        for name, stream in trial['alignment_files'].items():
            stream.write(trial['alignment_buffers'][name])
            stream.flush()
            trial['alignment_buffers'][name].clear()

    def record_window(self, result):
        if self.active:
            trial = self.active
            trial["windows_file"].write(json.dumps({
                "trial_sample_index": trial["samples"],
                "packets_seen": result.get("packets_seen"),
                "sqi": result.get("sqi"),
                "emotion": result.get("emotion"),
                "raw_interference": result.get("raw_interference"),
            }, ensure_ascii=False, allow_nan=False) + "\n")
            trial["windows_file"].flush()

    def finish(self, state, counters, self_report=None, browser_ended_at_ms=None):
        trial = self.active
        if trial is None:
            return
        try:
            self.flush()
            for key in ("raw_file", "sequence_file", "flags_file", "windows_file"):
                trial[key].close()
            for stream in trial['alignment_files'].values():
                stream.close()
            metadata = trial["metadata"]
            metadata.update(state=state, samples=trial["samples"],
                            duration_seconds=round(time.monotonic() - trial["started_mono"], 3),
                            board_ended_at=time.time(), end_counters=dict(counters),
                            browser_ended_at_ms=browser_ended_at_ms,
                            counter_deltas={key: int(counters[key]) - int(metadata["start_counters"][key])
                                            for key in metadata["start_counters"]},
                            self_report=self_report)
            if metadata['task'] == 'ssvep':
                metadata['board_ended_monotonic'] = time.monotonic()
            atomic_json(trial["directory"] / "metadata.json", metadata)
            self.active = None
            self.publish(state, {"path": str(trial["directory"]),
                                 "samples": trial["samples"]})
        finally:
            self.active = None

    def close(self, counters):
        if self.active:
            self.finish("service_stopped", counters)

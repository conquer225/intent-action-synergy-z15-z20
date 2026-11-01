"""Bounded length-prefixed JSON records. No pickle or remote execution."""
from dataclasses import dataclass
import json
import struct
import math
import re

MAX_RECORD_BYTES = 65536
CHANNELS = ("F3", "F4", "C3", "C4", "T7", "T8", "O1", "O2")
TASKS = ("emotion", "fatigue", "face", "sound", "stereo")
FEATURE_DIMENSIONS = dict(emotion=180, fatigue=20, sound=40)


@dataclass(frozen=True)
class Message:
    kind: str
    session: str
    sequence: int
    captured_ns: int
    body: dict


def _number(value):
    return type(value) in (int, float) and math.isfinite(value)


def validate(message):
    if (message.kind not in ("eeg", "features", "result", "environment", "command", "ping")
            or not isinstance(message.session, str)
            or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", message.session)
            or type(message.sequence) is not int or not 0 <= message.sequence < 2**63
            or type(message.captured_ns) is not int or not 0 <= message.captured_ns < 2**63
            or not isinstance(message.body, dict)):
        raise ValueError("invalid message envelope")
    body = message.body
    if message.kind == "eeg":
        samples = body.get("samples")
        if (body.get("sample_rate_hz") != 250 or tuple(body.get("channels", ())) != CHANNELS
                or not isinstance(samples, list) or not 1 <= len(samples) <= 250
                or any(not isinstance(row, list) or len(row) != 8
                       or not all(_number(v) for v in row) for row in samples)):
            raise ValueError("expected finite 250Hz sample-by-eight EEG in microvolts")
    elif message.kind == "features":
        task, vector = body.get("task"), body.get("vector")
        if (task not in FEATURE_DIMENSIONS or type(body.get("valid")) is not bool
                or not _number(body.get("quality")) or not 0 <= body["quality"] <= 1
                or any(not isinstance(body.get(key), str) or not 1 <= len(body[key]) <= limit
                       for key, limit in (("feature_version", 128), ("window_id", 128),
                                          ("source", 256), ("reason", 128)))):
            raise ValueError("invalid feature metadata")
        if body["valid"]:
            if (not isinstance(vector, list) or len(vector) != FEATURE_DIMENSIONS[task]
                    or not all(_number(v) and abs(v) <= 1e9 for v in vector)):
                raise ValueError("invalid feature vector")
        elif vector is not None:
            raise ValueError("invalid input must clear its feature vector")
        reference=body.get('original_reference')
        if reference is not None:
            if (not body['valid'] or not isinstance(reference,dict)
                    or reference.get('kind') not in ('HGB_regressor','SEED_linear')
                    or type(reference.get('class_id')) is not int or reference['class_id'] not in (0,1,2)):
                raise ValueError('invalid original-model reference')
            if reference['kind']=='HGB_regressor':
                if task!='fatigue' or not _number(reference.get('value')) or not 0<=reference['value']<=1:
                    raise ValueError('invalid HGB reference value')
            elif (task!='emotion' or not isinstance(reference.get('scores'),list) or len(reference['scores'])!=3
                    or not all(_number(v) for v in reference['scores'])):
                raise ValueError('invalid SEED reference scores')
    elif message.kind == "command":
        if body.get("op") == "key_event" and body.get("event") in ("key1_short", "key1_long", "key2_short"):
            return
        if body.get("op") == "set_mode" and body.get("mode") in ("idle", "face", "stereo"):
            return
        if body.get("op") == "set_audio" and type(body.get("enabled")) is bool:
            return
        raise ValueError("unsupported command")
    elif message.kind == "environment":
        from .environment import validate_environment
        validate_environment(body)
    elif message.kind == "result":
        valid = body.get("valid")
        task = body.get("task")
        if (task not in TASKS or type(valid) is not bool
                or not isinstance(body.get("model_version"), str) or not 1 <= len(body["model_version"]) <= 128
                or not isinstance(body.get("state"), str) or not 1 <= len(body["state"]) <= 128):
            raise ValueError("invalid result metadata")
        if valid and task != "stereo":
            scores = body.get("scores")
            if (type(body.get("class_id")) is not int or body["class_id"] not in (0, 1, 2)
                    or not isinstance(scores, list) or len(scores) != 3 or not all(_number(v) for v in scores)):
                raise ValueError("invalid three-class result")
        elif body.get("class_id") is not None or body.get("scores") is not None:
            raise ValueError("invalid results cannot retain a previous classification")
    elif body:
        raise ValueError("heartbeat body must be empty")


def encode(message):
    validate(message)
    version = 2 if (message.kind in ("features", "environment") or (message.kind == "result" and "window_id" in message.body)
                    or (message.kind == "command" and message.body.get("op") == "key_event")) else 1
    value = dict(version=version, kind=message.kind, session=message.session,
                 sequence=message.sequence, captured_ns=message.captured_ns, body=message.body)
    payload = json.dumps(value, allow_nan=False, separators=(",", ":")).encode("utf-8")
    if not 0 < len(payload) <= MAX_RECORD_BYTES:
        raise ValueError("record length outside limit")
    return struct.pack("!I", len(payload)) + payload


class Decoder:
    def __init__(self):
        self.buffer = bytearray()

    def feed(self, data):
        if len(data) > MAX_RECORD_BYTES + 4:
            raise ValueError("feed chunk exceeds limit")
        self.buffer.extend(data)
        messages = []
        while len(self.buffer) >= 4:
            length, = struct.unpack("!I", self.buffer[:4])
            if not 0 < length <= MAX_RECORD_BYTES:
                self.buffer.clear()
                raise ValueError("record length outside limit")
            if len(self.buffer) < 4 + length:
                break
            try:
                value = json.loads(self.buffer[4:4 + length], parse_constant=_reject_constant)
            except (UnicodeError, RecursionError, json.JSONDecodeError) as exc:
                self.buffer.clear()
                raise ValueError("invalid JSON record") from exc
            del self.buffer[:4 + length]
            if (not isinstance(value, dict) or type(value.get("version")) is not int
                    or value.get("version") not in (1, 2)
                    or (value.get("version") == 1 and value.get("kind") in ("features", "environment"))
                    or (value.get("version") == 1 and value.get("kind") == "command"
                        and isinstance(value.get("body"), dict) and value["body"].get("op") == "key_event")):
                raise ValueError("invalid version or message fields")
            value.pop("version")
            if set(value) != {"kind", "session", "sequence", "captured_ns", "body"}:
                raise ValueError("invalid version or message fields")
            message = Message(**value)
            validate(message)
            messages.append(message)
        return messages

    def finish(self):
        if self.buffer:
            self.buffer.clear()
            raise ValueError("connection ended during a record")


def _reject_constant(value):
    raise ValueError("non-finite JSON number")

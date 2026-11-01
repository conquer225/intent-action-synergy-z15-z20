"""Strict decoder for the connected IS4's self-described TTP/XDS records.

Wire facts come from the device captures and the credited protocol references.
No vendor runtime, fabricated coordinates or inference from camera pixels.
"""
from dataclasses import dataclass
import math
import struct


@dataclass(frozen=True)
class Tag:
    code: int
    values: tuple


class DecodeError(ValueError):
    pass


def decode(payload):
    if not 7 <= len(payload) <= 2 * 1024 * 1024:
        raise DecodeError("Invalid payload length")
    if payload[:2] != b"\0\0":
        raise DecodeError("Unexpected payload prefix")
    pos, fields = 2, 0

    def field(depth=0):
        nonlocal pos, fields
        fields += 1
        if depth > 8 or fields > 8192 or pos + 5 > len(payload):
            raise DecodeError("Truncated or excessively nested record")
        kind, size = struct.unpack_from(">BI", payload, pos)
        pos += 5
        if size > len(payload) - pos:
            raise DecodeError("Field extends past payload")
        body = payload[pos:pos + size]
        pos += size
        if kind == 5:
            if size != 4:
                raise DecodeError("Invalid tag length")
            tag = int.from_bytes(body, "big")
            count = (tag >> 16) & 0xfff
            return Tag(tag & 0xffff, tuple(field(depth + 1) for _ in range(count)))
        widths = {2: 4, 3: 4, 4: 8, 6: 8}
        if kind in widths:
            if size != widths[kind]:
                raise DecodeError("Invalid scalar length")
            value = int.from_bytes(body, "big", signed=kind != 2)
            return value / 65536 if kind == 3 else value / (2 ** 42) if kind == 4 else value
        if kind in (20, 21):
            if size < 4 or int.from_bytes(body[:4], "big") != size - 4:
                raise DecodeError("Invalid string/blob length")
            if kind == 21:
                return bytes(body[4:])
            try:
                return body[4:].decode("utf-8")
            except UnicodeDecodeError as exc:
                raise DecodeError("Invalid UTF-8 string") from exc
        raise DecodeError("Unsupported field type: " + str(kind))

    value = field()
    if pos != len(payload):
        raise DecodeError("Trailing data")
    return value


def gaze_columns(payload):
    row = decode(payload)
    if not isinstance(row, Tag) or row.code != 0x0bb8:
        raise DecodeError("Expected XDS row")
    result = {}
    for col in row.values:
        if not isinstance(col, Tag) or col.code != 0x0bb9 or len(col.values) != 2:
            raise DecodeError("Expected XDS column")
        ident, value = col.values
        if type(ident) is not int or ident in result:
            raise DecodeError("Invalid or duplicated column id")
        if isinstance(value, Tag) and value.code in (0x1f40, 0x1f41):
            width = 2 if value.code == 0x1f40 else 3
            if len(value.values) != width or any(type(v) not in (int, float) for v in value.values):
                raise DecodeError("Invalid point")
            value = value.values
        result[ident] = value
    return result


def is4_sample(payload):
    c = gaze_columns(payload)
    point = c.get(0x1c)
    has_point = isinstance(point, tuple) and len(point) == 2 and all(math.isfinite(v) for v in point)
    detected_l, detected_r = c.get(0x16) == 1, c.get(0x15) == 1
    # Conservative candidate gating pending a live calibrated-person capture.
    # Eye validity 4 and missing/zero combined validity are never actionable.
    valid_l = detected_l and c.get(7) == 0
    valid_r = detected_r and c.get(13) == 0
    usable = c.get(0x1b) == 1 and has_point and (valid_l or valid_r)
    on_screen = usable and all(0 <= v <= 1 for v in point)
    return {
        "timestamp_us": c.get(1), "frame_counter": c.get(0x14),
        "combined_validity": c.get(0x1b), "gaze": point if has_point else None,
        "left_detected": detected_l, "right_detected": detected_r,
        "left_validity": c.get(7), "right_validity": c.get(13),
        "left_pupil_mm": c.get(6), "right_pupil_mm": c.get(12),
        "usable_candidate": bool(usable), "on_screen_candidate": bool(on_screen),
    }

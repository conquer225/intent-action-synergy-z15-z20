"""Z15E v1, fixed binary contracts shared with net_protocol.h. No pickle/eval."""
from dataclasses import dataclass
import struct
import zlib
HEADER = struct.Struct("!4sBBH4I")
META = struct.Struct("!20H4I2H")
EYE = struct.Struct("!8H2I4B2H")
HELLO, FRAME, RESULT, COMMAND, STATUS = range(1, 6)
CHUNK, MAX_IMAGE, FRAME_DEADLINE = 1100, 640 * 480 * 3, 0.22
@dataclass(frozen=True)
class Packet:
    kind: int
    session: int
    sequence: int
    sampled_ms: int
    payload: bytes
def encode(kind, session, sequence, sampled_ms, payload=b""):
    if kind not in range(1, 6) or len(payload) > 1176:
        raise ValueError("packet type/length")
    head = struct.pack("!4sBBH3I", b"Z15E", 1, kind, len(payload), session, sequence, sampled_ms)
    return head + struct.pack("!I", zlib.crc32(head + payload)) + payload
def decode(data):
    if not 24 <= len(data) <= 1200:
        raise ValueError("packet length")
    magic, version, kind, length, session, seq, ms, crc = HEADER.unpack_from(data)
    if magic != b"Z15E" or version != 1 or kind not in range(1, 6) or length != len(data) - 24:
        raise ValueError("packet header")
    if zlib.crc32(data[:20] + data[24:]) != crc:
        raise ValueError("packet checksum")
    return Packet(kind, session, seq, ms, data[24:])
def newer(a, b):
    return 0 < ((a - b) & 0xffffffff) < 0x80000000
@dataclass(frozen=True)
class Frame:
    packet: Packet
    metadata: bytes
    image: bytes
    received: float
    @property
    def fields(self):
        return META.unpack(self.metadata)
def validate_metadata(payload):
    if len(payload) < META.size:
        raise ValueError("short frame")
    fields = META.unpack_from(payload)
    x, y, w, h, iw, ih, cw, ch = fields[:8]
    flags, total, crc, offset, index, count = fields[20:]
    if not (64 <= iw <= 640 and 64 <= ih <= 480 and 64 <= cw <= 4096 and 64 <= ch <= 4096
            and w > 0 and h > 0 and x + w <= cw and y + h <= ch and flags <= 7
            and 0 < total <= MAX_IMAGE and (bool(flags & 4) or total == iw * ih * 3) and count == (total + CHUNK - 1) // CHUNK
            and index < count and offset == index * CHUNK and len(payload) - META.size == min(CHUNK, total - offset)):
        raise ValueError("frame geometry/chunk")
    if flags & 2:
        fx, fy, fw, fh = fields[8:12]
        if fw < 32 or fh < 32 or fx + fw > cw or fy + fh > ch:
            raise ValueError("anchor face")
        for pos in (12, 16):
            rx, ry, rw, rh = fields[pos:pos + 4]
            if rw < 8 or rh < 6 or rx + rw > cw or ry + rh > ch:
                raise ValueError("anchor ROI")
    return fields
class Reassembler:
    """One frame, one epoch, bounded lifetime; never concatenate unrelated captures."""
    def __init__(self):
        self.reset()
        self.dropped = 0
    def reset(self):
        self.key = self.meta = self.buffer = None
        self.parts = set()
        self.started = 0.0
        self.last_sequence = None
    def push(self, packet, now):
        if packet.kind != FRAME:
            raise ValueError("expected frame")
        fields = validate_metadata(packet.payload)
        key = (packet.session, packet.sequence, packet.sampled_ms)
        canonical = packet.payload[:52]
        total, offset, index, count = fields[21], fields[23], fields[24], fields[25]
        if self.key != key:
            if self.last_sequence is not None and not newer(packet.sequence, self.last_sequence):
                return None
            if self.buffer is not None:
                self.dropped += 1
            self.key, self.meta = key, canonical
            self.last_sequence = packet.sequence
            self.buffer, self.parts, self.started = bytearray(total), set(), now
        if self.buffer is None or now - self.started > FRAME_DEADLINE:
            self.buffer = None
            return None
        if canonical != self.meta:
            self.buffer = None
            raise ValueError("inconsistent frame metadata")
        data = packet.payload[60:]
        if index in self.parts:
            if self.buffer[offset:offset + len(data)] != data:
                self.buffer = None
                raise ValueError("conflicting duplicate")
            return None
        self.buffer[offset:offset + len(data)] = data
        self.parts.add(index)
        if len(self.parts) != count:
            return None
        image = bytes(self.buffer)
        self.buffer = None
        if zlib.crc32(image) != fields[22]:
            raise ValueError("frame checksum")
        metadata = canonical + struct.pack("!IHH", 0, 0, count)
        return Frame(packet, metadata, image, self.started)
def unpack_result(payload):
    if len(payload) != 80:
        raise ValueError("result length")
    face = struct.unpack_from("!4H", payload)
    eyes = []
    for pos in (8, 40):
        fields = EYE.unpack_from(payload, pos)
        eyes.append(dict(detected=fields[:4], analyzed=fields[4:8], x=fields[8] / 256,
                         y=fields[9] / 256, valid=fields[10], quality=fields[11],
                         contrast=fields[12], reason=fields[13]))
    return dict(face=face, left=eyes[0], right=eyes[1], process_ms=struct.unpack_from("!I", payload, 72)[0],
                pair=bool(struct.unpack_from("!I", payload, 76)[0]))

def jpeg_dimensions(data):
    """Read SOF without allocating decoder memory from untrusted dimensions."""
    if not data.startswith(b"\xff\xd8"):
        raise ValueError("JPEG signature")
    pos = 2
    while pos < len(data):
        if data[pos] != 255:
            raise ValueError("JPEG marker")
        while pos < len(data) and data[pos] == 255:
            pos += 1
        if pos >= len(data):
            break
        marker = data[pos]
        pos += 1
        if marker in (0, 0xd8, 0xd9, 0xda):
            raise ValueError("JPEG missing SOF")
        if marker == 1 or 0xd0 <= marker <= 0xd7:
            continue
        if pos + 2 > len(data):
            break
        length = int.from_bytes(data[pos:pos + 2], "big")
        if length < 2 or pos + length > len(data):
            raise ValueError("JPEG segment length")
        if marker in (0xc0, 0xc1, 0xc2):
            if length != 17 or data[pos + 2] != 8 or data[pos + 7] != 3:
                raise ValueError("JPEG color format")
            return (int.from_bytes(data[pos + 5:pos + 7], "big"),
                    int.from_bytes(data[pos + 3:pos + 5], "big"))
        if 0xc0 <= marker <= 0xcf and marker not in (0xc4, 0xc8, 0xcc):
            raise ValueError("unsupported JPEG SOF")
        pos += length
    raise ValueError("JPEG missing SOF")

def decode_image(frame):
    import numpy as np
    iw, ih = frame.fields[4:6]
    if frame.fields[20] & 4:
        if jpeg_dimensions(frame.image) != (iw, ih):
            raise ValueError("JPEG dimensions")
        import cv2
        image = cv2.imdecode(np.frombuffer(frame.image, dtype=np.uint8), cv2.IMREAD_COLOR)
        if image is None or image.shape != (ih, iw, 3):
            raise ValueError("JPEG decoding")
        return image
    return np.frombuffer(frame.image, dtype=np.uint8).reshape(ih, iw, 3).copy()

def validate_status(state, nonce):
    if not isinstance(state, dict) or state.get("nonce") != nonce or state.get("source") not in ("PC", "LOCAL"):
        raise ValueError("status identity/source")
    limits = dict(pair=1, stable=3, cal=7, stage=3, failed=1, valid=1, dir=3, armed=1,
                  dwell=10000, pause=31, error=3, retry=3, cmdok=1)
    for name in ("event", "sample", "detect_ms", "period_ms", "accepted", "rejected", "timeouts", "cmdseq"):
        limits[name] = 0xffffffff
    for name, limit in limits.items():
        if type(state.get(name)) is not int or not 0 <= state[name] <= limit:
            raise ValueError("status scalar: " + name)
    for name, count, limit in (("nx", 2, 256), ("eye_valid", 2, 1), ("counts", 2, 16)):
        values = state.get(name)
        if not isinstance(values, list) or len(values) != count or any(type(x) is not int or not 0 <= x <= limit for x in values):
            raise ValueError("status vector: " + name)
    for name, count, limit in (("pupil", 2, 4096), ("refs", 3, 256)):
        values = state.get(name)
        if not isinstance(values, list) or len(values) != 2 or any(not isinstance(row, list) or len(row) != count
                or any(type(x) is not int or not 0 <= x <= limit for x in row) for row in values):
            raise ValueError("status geometry: " + name)
    return state

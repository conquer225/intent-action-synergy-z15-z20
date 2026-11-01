"""Wire protocol shared by calibration UI and offline tests; no third-party dependencies."""
from functools import reduce
from operator import xor

WIDTH, HEIGHT = 320, 240


def roi_packet(x: int, y: int, width: int, height: int, threshold: int) -> bytes:
    if not (0 <= x < WIDTH and 0 <= y < HEIGHT and 16 <= width <= 255
            and 8 <= height <= 255 and x + width <= WIDTH and y + height <= HEIGHT
            and 1 <= threshold <= 255):
        raise ValueError("ROI 必须在 320×240 图内，宽至少 16、高至少 8，阈值 1–255")
    payload = bytes((x >> 8, x & 255, y, width, height, threshold))
    return b"\xa5" + payload + bytes((reduce(xor, payload), 0x5A))


def parse_status(line: bytes) -> dict:
    fields = line.decode("ascii").strip().split()
    if len(fields) != 16 or fields[0] != "EYE" or fields[1] not in ("I", "L", "C", "R"):
        raise ValueError("invalid status frame")
    result = {"direction": fields[1]}
    schema = (("V",1,1),("F",1,1),("C",1,7),("A",1,3),("X",3,319),
              ("N",4,65535),("Q",2,255),("E",4,65535),("D",1,0),
              ("S",1,1),("I",4,65535),("R",1,1),("!",1,1),("K",1,1))
    for field, (key, width, maximum) in zip(fields[2:], schema):
        if len(field) != width + 1 or field[0] != key:
            raise ValueError("invalid status field")
        value = field[1:]
        if key == "D":
            if value not in ("I", "L", "C", "R"):
                raise ValueError("invalid event direction")
            result[key] = value
        else:
            if any(c not in "0123456789ABCDEFabcdef" for c in value) or int(value,16) > maximum:
                raise ValueError("invalid status value")
            result[key] = int(value,16)
    return result


class Decoder:
    """Handles arbitrary USB packet boundaries; binary images never parsed as text."""
    def __init__(self):
        self.buffer = bytearray()
        self.image_bytes = 0

    def feed(self, data: bytes):
        self.buffer.extend(data)
        messages = []
        while self.buffer:
            if self.image_bytes:
                if len(self.buffer) < self.image_bytes:
                    break
                messages.append(("image", bytes(self.buffer[:self.image_bytes])))
                del self.buffer[:self.image_bytes]
                self.image_bytes = 0
            elif self.buffer.startswith(b"ZIMG"):
                if len(self.buffer) < 8:
                    break
                if self.buffer[4:8] != b"\x40\x01\xf0\x00":
                    del self.buffer[0]
                    continue
                del self.buffer[:8]
                self.image_bytes = WIDTH * HEIGHT
            elif self.buffer.startswith(b"EYE "):
                end = self.buffer.find(b"\n")
                if end < 0:
                    if len(self.buffer) > 256:
                        del self.buffer[0]
                        continue
                    break
                line = bytes(self.buffer[:end+1])
                del self.buffer[:end+1]
                try:
                    messages.append(("status", parse_status(line)))
                except (ValueError, UnicodeDecodeError):
                    messages.append(("error", "状态帧损坏，请检查波特率或复位板卡"))
            elif any(prefix.startswith(self.buffer) for prefix in (b"ZIMG", b"EYE ")):
                break
            else:
                del self.buffer[0]
        return messages

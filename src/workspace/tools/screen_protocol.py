"""Version 2 screen gaze protocol. Recognition always runs on the FPGA."""
from functools import reduce
from operator import xor

WIDTH, HEIGHT = 320, 240


def eye_packet(slot, x, y, w, h, dark, bright):
    if not (slot in (0, 1) and 0 <= x < 640 and 0 <= y < 480 and
            24 <= w <= 160 and 12 <= h <= 96 and x + w <= 640 and y + h <= 480
            and 8 <= dark and dark + 16 <= bright <= 248):
        raise ValueError("眼框须在 640×480 内，宽 24–160、高 12–96；暗阈值至少 8，亮阈值至少高 16，最高 248。")
    data = bytes((slot, x >> 8, x & 255, y >> 8, y & 255, w, h, dark, bright))
    return b"\xb5" + data + bytes((reduce(xor, data), 0x5a))


def parse_status(line):
    parts = line.decode("ascii").strip().split()
    schema = (("V", 1, 1), ("F", 1, 3), ("M", 1, 5), ("C", 1, 7),
              ("P", 2, 31), ("T", 1, 1), ("H", 1, 15), ("G", 1, 15), ("A", 1, 1),
              ("X", 2, 255), ("Y", 2, 255), ("E", 4, 65535), ("D", 1, 0),
              ("S", 1, 1), ("I", 4, 65535), ("R", 1, 1), ("!", 1, 1))
    if len(parts) != len(schema) + 2 or parts[0] != "SCR" or parts[1] not in ("I", "L", "C", "R"):
        raise ValueError("wrong status version/length")
    result = {"direction": parts[1]}
    for field, (key, width, maximum) in zip(parts[2:], schema):
        if len(field) != width + 1 or field[0] != key:
            raise ValueError("wrong status field")
        value = field[1:]
        if key == "D":
            if value not in ("I", "L", "C", "R"):
                raise ValueError("wrong event direction")
            result[key] = value
        else:
            if any(c not in "0123456789ABCDEFabcdef" for c in value) or int(value, 16) > maximum:
                raise ValueError("wrong status value")
            result[key] = int(value, 16)
    return result


class Decoder:
    def __init__(self):
        self.buffer = bytearray()
        self.image_bytes = 0

    def feed(self, data):
        self.buffer.extend(data)
        messages = []
        prefixes = (b"SCR ", b"ZIMG", b"RCFG", b"EYE ")
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
                if self.buffer[4:8] == b"\x40\x01\xf0\x00":
                    del self.buffer[:8]
                    self.image_bytes = 76800
                else:
                    del self.buffer[0]
            elif self.buffer.startswith(b"RCFG"):
                if len(self.buffer) < 14:
                    break
                payload = bytes(self.buffer[4:13])
                if reduce(xor, payload) == self.buffer[13]:
                    messages.append(("ack", payload))
                else:
                    messages.append(("error", "参数确认包校验失败，请重新应用。"))
                del self.buffer[:14]
            elif self.buffer.startswith((b"SCR ", b"EYE ")):
                end = self.buffer.find(b"\n")
                if end < 0:
                    if len(self.buffer) > 256:
                        del self.buffer[0]
                        continue
                    break
                line = bytes(self.buffer[:end+1])
                del self.buffer[:end+1]
                if line.startswith(b"EYE "):
                    messages.append(("error", "检测到旧版单眼固件：请下载 z15_screen_top.bit。"))
                else:
                    try:
                        messages.append(("status", parse_status(line)))
                    except (ValueError, UnicodeDecodeError):
                        messages.append(("error", "状态帧损坏，请检查串口或复位。"))
            elif any(p.startswith(self.buffer) for p in prefixes):
                break
            else:
                del self.buffer[0]
        return messages

import ctypes as C
from pathlib import Path
FIELDS = ("source pair stable cal stage failed valid dir armed dwell event sample left_nx right_nx "
          "left_x left_y right_x right_y left_valid right_valid left_count right_count "
          "ll lc lr rl rc rr pause track error retry detect_ms period_ms accepted rejected timeouts commit result_ms").split()
class BoardCore:
    def __init__(self, library):
        self.lib = C.CDLL(str(Path(library).resolve()))
        self.lib.board_prepare.argtypes = [C.c_void_p, C.c_uint32, C.c_uint32, C.c_uint32, C.c_uint32, C.c_void_p, C.c_void_p]
        self.lib.board_probe_prepare.argtypes = self.lib.board_prepare.argtypes
        self.lib.board_packet.argtypes = [C.c_void_p, C.c_uint32, C.c_uint32]
        self.lib.board_probe_packet.argtypes = self.lib.board_packet.argtypes
        self.lib.board_local.argtypes = [C.c_void_p, C.c_uint32, C.c_uint32, C.c_uint32]
        self.lib.board_status.argtypes = [C.c_void_p, C.c_uint]
        for name in ("board_timeout", "board_command"):
            getattr(self.lib, name).restype = C.c_int
        self.lib.board_init()
        self.pixels = C.create_string_buffer(640 * 480 * 3)
        self.meta = C.create_string_buffer(60)
    def source(self, source):
        return bool(self.lib.board_source(int(source)))
    def reset(self):
        self.lib.board_reset()
    def prepare(self, image, sampled, seq, session, probe=False):
        data = image if isinstance(image, bytes) else image.tobytes()
        method = self.lib.board_probe_prepare if probe else self.lib.board_prepare
        count = method(data, len(data), sampled, seq, session, self.meta, self.pixels)
        if not count:
            raise ValueError("board crop input/state")
        return self.meta.raw, self.pixels.raw[:count]
    def accept(self, packet, now):
        return bool(self.lib.board_packet(packet, len(packet), now))
    def timeout(self, now):
        return bool(self.lib.board_timeout(now))
    def command(self, code, now):
        return bool(self.lib.board_command(ord(code), now))
    def local(self, image, now, sequence=0):
        data = image if isinstance(image, bytes) else image.tobytes()
        return self.lib.board_local(data, len(data), now, sequence)
    def state(self):
        values = (C.c_uint32 * len(FIELDS))()
        if self.lib.board_status(values, len(FIELDS)) != len(FIELDS):
            raise RuntimeError("board state ABI")
        raw = dict(zip(FIELDS, values))
        return dict(source="PC" if raw["source"] else "LOCAL", pair=raw["pair"], stable=raw["stable"],
                    cal=raw["cal"], stage=raw["stage"], failed=raw["failed"], valid=raw["valid"], dir=raw["dir"],
                    armed=raw["armed"], dwell=raw["dwell"], event=raw["event"], sample=raw["sample"],
                    nx=[raw["left_nx"], raw["right_nx"]], pupil=[[raw["left_x"], raw["left_y"]], [raw["right_x"], raw["right_y"]]],
                    eye_valid=[raw["left_valid"], raw["right_valid"]], counts=[raw["left_count"], raw["right_count"]],
                    refs=[[raw["ll"], raw["lc"], raw["lr"]], [raw["rl"], raw["rc"], raw["rr"]]],
                    **{key: raw[key] for key in ("pause", "track", "error", "retry", "detect_ms", "period_ms",
                                               "accepted", "rejected", "timeouts", "commit", "result_ms")})

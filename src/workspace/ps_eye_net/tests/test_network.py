"""Real native controller + real loopback UDP; all images stay on this host."""
import ctypes as C
import json
import socket
import struct
import sys
import time
import unittest
import zlib
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "linux"))
import numpy as np
from net_protocol import *
from pc_receiver import Receiver, NativeDetector
from board_core import BoardCore
from board_service import Service, chunks, now_ms
IMAGE = np.full((720, 1280, 3), 160, np.uint8)

def metadata(iw=64, ih=64, flags=0, pixels=None):
    data = bytes(iw * ih * 3) if pixels is None else pixels
    return META.pack(0, 0, iw, ih, iw, ih, 1280, 720, *([0] * 12),
                     flags, len(data), zlib.crc32(data), 0, 0, (len(data) + CHUNK - 1) // CHUNK), data

def measured(nx=128, shift=(0, 0), detected_shift=0, analyzed_shift=0, valid=(1, 1)):
    dx, dy = shift
    face = (300 + dx, 200 + dy, 600, 400)
    eyes = []
    for i, x in enumerate((360, 700)):
        detected = (x + dx + detected_shift, 260 + dy, 100, 50)
        analyzed = (x + dx + analyzed_shift, 260 + dy, 100, 50)
        px = (x + dx) * 256 + nx * 100
        py = (280 + dy) * 256
        eyes.append(EYE.pack(*detected, *analyzed, px, py, valid[i], 100, 100, 1 if valid[i] else 3, 20, 100))
    return struct.pack("!4H", *face) + b"".join(eyes) + struct.pack("!II", 1, 1)

def empty_status(nonce):
    return dict(nonce=nonce, source="PC", pair=0, stable=0, cal=0, stage=0, failed=0,
                valid=0, dir=0, armed=1, dwell=0, pause=0, error=0, retry=0, cmdok=0,
                event=0, sample=0, detect_ms=0, period_ms=0, accepted=0, rejected=0, timeouts=0,
                cmdseq=0, nx=[0, 0], eye_valid=[0, 0], counts=[0, 0], pupil=[[0, 0], [0, 0]], refs=[[0, 0, 0], [0, 0, 0]])

class ProtocolTests(unittest.TestCase):
    def test_c_encoder_matches_python_wire_bytes(self):
        lib = C.CDLL(str(ROOT / "tests/board_core.dll"))
        lib.net_encode.argtypes = [C.c_void_p, C.c_uint8, C.c_uint32, C.c_uint32, C.c_uint32, C.c_void_p, C.c_uint16]
        data = bytes(range(256))
        output = C.create_string_buffer(1200)
        n = lib.net_encode(output, RESULT, 0xabcdef12, 0xfffffffe, 0x80000001, data, len(data))
        self.assertEqual(output.raw[:n], encode(RESULT, 0xabcdef12, 0xfffffffe, 0x80000001, data))
        self.assertEqual(lib.net_encode(output, RESULT, 1, 1, 1, data, 1177), 0)
    def test_crc_length_and_type(self):
        packet = encode(RESULT, 0xabcdef12, 0xffffffff, 123, bytes(80))
        self.assertEqual(decode(packet).sequence, 0xffffffff)
        for bad in (packet[:-1], packet + b"x", packet[:30] + bytes([packet[30] ^ 1]) + packet[31:], b"x", bytes(1201)):
            with self.assertRaises(ValueError): decode(bad)
        self.assertTrue(newer(1, 0xffffffff))
        self.assertFalse(newer(0xffffffff, 1))
    def test_status_rejects_malformed_ui_shapes(self):
        state = empty_status(123)
        self.assertEqual(validate_status(state, 123), state)
        for key, value in (("nx", 1), ("counts", [1]), ("pupil", [[0, 0], "bad"]), ("source", "unknown"), ("stage", 4)):
            with self.assertRaises(ValueError): validate_status(dict(state, **{key: value}), 123)
    def test_out_of_order_duplicate_expiry_crc(self):
        meta, pixels = metadata()
        packets = [decode(p) for p in chunks(meta, pixels, 3, 1, 100, False)]
        r = Reassembler()
        self.assertIsNone(r.push(packets[-1], 1))
        self.assertIsNone(r.push(packets[-1], 1.001))
        complete = None
        for p in reversed(packets[:-1]): complete = r.push(p, 1.002)
        self.assertEqual(complete.image, pixels)
        self.assertIsNone(r.push(packets[0], 1.003))
        r.reset(); r.push(packets[0], 1)
        self.assertIsNone(r.push(packets[1], 1.221))
        r.reset(); r.push(packets[0], 1)
        bad = Packet(FRAME, 3, 1, 100, packets[0].payload[:-1] + b"x")
        with self.assertRaises(ValueError): r.push(bad, 1.01)
        r.reset()
        p = packets[-1]
        packets[-1] = Packet(FRAME, 3, 1, 100, p.payload[:-1] + b"x")
        with self.assertRaises(ValueError):
            for p in packets: r.push(p, 1)
    def test_metadata_memory_and_jpeg_dimensions(self):
        meta, pixels = metadata()
        parts = [decode(p) for p in chunks(meta, pixels, 3, 1, 100, True)]
        r = Reassembler()
        frame = None
        for p in parts: frame = r.push(p, 1)
        self.assertEqual(decode_image(frame).shape, (64, 64, 3))
        import cv2
        ok, other = cv2.imencode(".jpg", np.zeros((65, 64, 3), np.uint8))
        self.assertTrue(ok)
        with self.assertRaises(ValueError): decode_image(Frame(frame.packet, frame.metadata, other.tobytes(), 1))
        fields = list(META.unpack(meta)); fields[21] = MAX_IMAGE + 1
        with self.assertRaises(ValueError): validate_metadata(META.pack(*fields) + pixels[:CHUNK])
        for data in (b"", b"\xff\xd8\xff\xe0\x00\x01", b"\xff\xd8\xff\xda\x00\x02"):
            with self.assertRaises(ValueError): jpeg_dimensions(data)
    def test_native_uniform_never_invents_pupils(self):
        meta, pixels = metadata()
        f = Frame(Packet(FRAME, 1, 1, 1, b""), meta, pixels, time.monotonic())
        result = unpack_result(NativeDetector().infer(f))
        self.assertFalse(result["pair"])
        self.assertFalse(result["left"]["valid"])
        self.assertFalse(result["right"]["valid"])

class ControllerTests(unittest.TestCase):
    def setUp(self):
        self.core = BoardCore(ROOT / "tests/board_core.dll")
        self.core.source(1)
        self.seq, self.ms = 0, 1000
    def begin(self):
        self.seq += 1; self.ms = (self.ms + 100) & 0xffffffff
        return self.core.prepare(IMAGE, self.ms, self.seq, 42)
    def feed(self, nx=128, **kw):
        self.begin()
        self.assertTrue(self.core.accept(encode(RESULT, 42, self.seq, self.ms, measured(nx, **kw)), self.ms + 10))
    def sample(self, nx, n):
        for _ in range(n): self.feed(nx)
    def calibrate(self):
        self.sample(128, 3)
        self.assertTrue(self.core.command("c", self.ms + 10))
        self.sample(32, 37)
        for nx in (128, 224): self.sample(nx, 36)
        s = self.core.state()
        self.assertEqual((s["cal"], s["stage"], s["failed"]), (7, 0, 0))
        self.assertEqual(s["refs"], [[32, 128, 224], [32, 128, 224]])
    def test_full_calibration_dwell_no_repeat_center_rearm(self):
        self.calibrate()
        self.sample(32, 14)
        self.assertEqual(self.core.state()["event"], 1)
        self.sample(32, 30)
        self.assertEqual(self.core.state()["event"], 1)
        self.feed(224, valid=(0, 1))
        self.assertFalse(self.core.state()["valid"])
        self.sample(224, 20)
        self.assertEqual(self.core.state()["event"], 1)
        self.sample(128, 10); self.sample(224, 14)
        self.assertEqual(self.core.state()["event"], 2)
        self.assertTrue(self.core.source(0))
        self.assertEqual((self.core.state()["cal"], self.core.state()["valid"]), (0, 0))
    def test_session_sequence_age_geometry_and_timeout(self):
        self.sample(128, 3)
        self.begin()
        result = measured()
        for epoch, seq, ms, now in ((41, self.seq, self.ms, self.ms + 1),
                                    (42, self.seq - 1, self.ms, self.ms + 1),
                                    (42, self.seq, self.ms - 1, self.ms + 1),
                                    (42, self.seq, self.ms, self.ms + 221)):
            self.assertFalse(self.core.accept(encode(RESULT, epoch, seq, ms, result), now))
        self.assertFalse(self.core.accept(encode(RESULT, 42, self.seq, self.ms, measured(analyzed_shift=1)), self.ms + 2))
        outside = bytearray(result)
        struct.pack_into("!4H", outside, 0, 170, 200, 650, 400)
        self.assertFalse(self.core.accept(encode(RESULT, 42, self.seq, self.ms, bytes(outside)), self.ms + 2))
        self.assertFalse(self.core.timeout(self.ms + 220))
        self.assertTrue(self.core.timeout(self.ms + 221))
        self.assertFalse(self.core.state()["valid"])
        self.assertEqual(self.core.state()["timeouts"], 1)
        self.assertFalse(self.core.command("c", self.ms + 222))
    def test_head_projection_retains_gaze_and_calibration_pause(self):
        self.sample(128, 3); self.assertTrue(self.core.command("c", self.ms + 10))
        self.sample(32, 37)
        self.sample(128, 25)
        count = self.core.state()["counts"]
        self.feed(128, valid=(0, 0))
        self.assertEqual(self.core.state()["counts"], count)
        self.assertEqual(self.core.state()["cal"], 1)
        self.feed(128, shift=(10, 5))
        self.assertEqual(self.core.state()["nx"], [128, 128])
        self.feed(150, shift=(10, 5), detected_shift=10)
        self.assertEqual(self.core.state()["nx"], [150, 150])
        self.begin()
        self.assertFalse(self.core.accept(encode(RESULT, 42, self.seq, self.ms,
                                                measured(150, detected_shift=10, analyzed_shift=10)), self.ms + 1))
        self.assertTrue(self.core.command("r", self.ms + 10))
        self.assertFalse(self.core.lib.board_waiting())
        self.assertFalse(self.core.accept(encode(RESULT, 42, self.seq, self.ms, measured()), self.ms + 2))
    def test_timer_wrap(self):
        self.ms = 0xffffff00
        self.sample(128, 4)
        self.assertEqual(self.core.state()["period_ms"], 100)
        self.assertEqual(self.core.state()["accepted"], 4)
    def test_quality_subpixel_bounds_and_truncated_results(self):
        self.begin()
        variants = []
        for offset, value in ((8 + 24, 2), (8 + 25, 31), (8 + 25, 129), (8 + 26, 7), (8 + 27, 0)):
            p = bytearray(measured()); p[offset] = value; variants.append(bytes(p))
        for offset, value, fmt in ((24, 460 * 256, "!I"), (28, 310 * 256, "!I"), (24, 0xffffffff, "!I"),
                                   (36, 5, "!H"), (36, 101, "!H"), (38, 12289, "!H")):
            p = bytearray(measured()); struct.pack_into(fmt, p, offset, value); variants.append(bytes(p))
        variants.extend((measured()[:-1], measured() + b"x"))
        for result in variants:
            self.assertFalse(self.core.accept(encode(RESULT, 42, self.seq, self.ms, result), self.ms + 10))
        self.assertTrue(self.core.accept(encode(RESULT, 42, self.seq, self.ms, measured()), self.ms + 10))
    def test_stale_calibration_request_is_rejected(self):
        self.sample(128, 3)
        self.assertFalse(self.core.command("c", self.ms + 261))
        self.assertFalse(self.core.command("t", self.ms + 10))
        self.assertTrue(self.core.command("c", self.ms + 10))
    def test_crop_covers_whole_face_and_pixel_center_mapping(self):
        self.feed()
        columns = np.arange(1280, dtype=np.uint16) % 256
        rows = np.arange(720, dtype=np.uint16) % 256
        image = np.zeros_like(IMAGE)
        image[:, :, 0] = columns
        image[:, :, 1] = rows[:, None]
        meta, pixels = self.core.prepare(image, self.ms + 100, self.seq + 1, 42)
        x, y, w, h, iw, ih = META.unpack(meta)[:6]
        self.assertEqual((x, y, w, h, iw, ih), (180, 120, 840, 560, 640, 426))
        self.assertLessEqual(x, 300); self.assertGreaterEqual(x + w, 900)
        output = np.frombuffer(pixels, np.uint8).reshape(ih, iw, 3)
        xx = x + ((2 * np.arange(iw) + 1) * w) // (2 * iw)
        yy = y + ((2 * np.arange(ih) + 1) * h) // (2 * ih)
        np.testing.assert_array_equal(output, image[yy[:, None], xx[None, :]])
    def test_crop_retains_window_under_detector_jitter_and_reacquires(self):
        self.feed()
        self.feed()
        first, _ = self.begin()
        geometry = META.unpack(first)[:8]
        self.assertTrue(self.core.accept(encode(RESULT, 42, self.seq, self.ms, measured(shift=(20, 10))), self.ms + 10))
        held, _ = self.begin()
        self.assertEqual(META.unpack(held)[:8], geometry)
        self.assertTrue(self.core.accept(encode(RESULT, 42, self.seq, self.ms, measured(shift=(100, 0))), self.ms + 10))
        moved, _ = self.begin()
        self.assertNotEqual(META.unpack(moved)[:8], geometry)
        self.assertTrue(self.core.accept(encode(RESULT, 42, self.seq, self.ms, bytes(80)), self.ms + 10))
        search, _ = self.begin()
        self.assertEqual(META.unpack(search)[:6], (0, 0, 1280, 720, 640, 360))
        self.assertTrue(META.unpack(search)[20] & 1)

class MockVideo:
    def __init__(self): self.clears = self.published = 0; self.closed = False
    def clear(self): self.clears += 1
    def snapshot(self): return IMAGE
    def publish(self, *args): self.published += 1
    def close(self): self.closed = True

def receive_kind(sock, kind, timeout=1):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        try:
            data, peer = sock.recvfrom(1201)
            p = decode(data)
            if p.kind == kind: return p, peer
        except socket.timeout: pass
    raise AssertionError("UDP kind not received: " + str(kind))

class SocketTests(unittest.TestCase):
    def test_recovery_probe_only_switches_on_fresh_response(self):
        class Detector:
            def infer(self, frame): return bytes(80)
        core, video = BoardCore(ROOT / "tests/board_core.dll"), MockVideo()
        service = Service(core, video, "127.0.0.1", 0)
        receiver = Receiver("127.0.0.1", service.socket.getsockname()[1], local_port=0, detector=Detector())
        receiver.start()
        try:
            deadline = time.monotonic() + 2
            while service.peer is None and time.monotonic() < deadline:
                service.pump(); time.sleep(.005)
            self.assertIsNotNone(service.peer)
            # First simulate retry while no PC answer is available.
            receiver.close()
            service.cooldown_until = time.monotonic() - 1
            clears = video.clears
            service.step()
            self.assertEqual(core.state()["source"], "LOCAL")
            self.assertEqual(video.clears, clears)
            self.assertGreater(service.cooldown_until, time.monotonic())
            # Fresh peer re-handshake first, then force LOCAL retry with a valid PC.
            service.peer_time -= 2
            receiver = Receiver("127.0.0.1", service.socket.getsockname()[1], local_port=0, detector=Detector())
            receiver.start()
            deadline = time.monotonic() + 2
            old_nonce = service.nonce
            while service.nonce == old_nonce and time.monotonic() < deadline:
                service.pump(); time.sleep(.005)
            service.cooldown_until = time.monotonic() - 1
            self.assertEqual(core.state()["source"], "LOCAL")
            service.step()
            self.assertEqual(core.state()["source"], "PC")
            self.assertEqual(core.state()["accepted"], 1)
        finally:
            if receiver.is_alive(): receiver.close()
            service.close()
    def test_real_service_pc_roundtrip_and_fallback(self):
        core, video = BoardCore(ROOT / "tests/board_core.dll"), MockVideo()
        service = Service(core, video, "127.0.0.1", 0)
        port = service.socket.getsockname()[1]
        receiver = Receiver("127.0.0.1", port, local_port=0)
        receiver.start()
        try:
            deadline = time.monotonic() + 2
            while service.peer is None and time.monotonic() < deadline:
                service.pump(); time.sleep(.005)
            self.assertIsNotNone(service.peer)
            for _ in range(4): service.step()
            self.assertGreaterEqual(core.state()["accepted"], 3)
            self.assertEqual(core.state()["event"], 0)
            self.assertFalse(core.state()["valid"])
            self.assertEqual(core.state()["source"], "PC")
            receiver.command("r")
            deadline = time.monotonic() + 1
            while receiver.last_control is None and time.monotonic() < deadline:
                service.pump(); time.sleep(.005)
            self.assertTrue(receiver.last_control["accepted"])
            self.assertEqual(receiver.last_control["code"], "r")
            receiver.close()
            service.peer_time -= 2
            service.step()
            self.assertEqual(core.state()["source"], "LOCAL")
            self.assertEqual(core.state()["cal"], 0)
        finally:
            if receiver.is_alive(): receiver.close()
            service.close()
        self.assertTrue(video.closed)
    def test_dropped_fragment_and_lost_result_retransmission(self):
        class Detector:
            calls = 0
            def infer(self, frame): self.calls += 1; return bytes(80)
        board = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        board.bind(("127.0.0.1", 0)); board.settimeout(.05)
        detector = Detector()
        receiver = Receiver("127.0.0.1", board.getsockname()[1], local_port=0, detector=detector)
        receiver.start()
        try:
            hello, peer = receive_kind(board, HELLO)
            nonce = struct.unpack("!I", hello.payload)[0]
            board.sendto(encode(STATUS, 99, 1, 0, json.dumps(empty_status(nonce)).encode()), peer)
            time.sleep(.01)
            meta, data = metadata()
            packets = chunks(meta, data, 99, 1, 123, False)
            for p in reversed(packets[1:]): board.sendto(p, peer)
            board.sendto(packets[-1], peer)
            board.sendto(packets[0], peer)  # bounded retry repairs the missing first fragment
            first, _ = receive_kind(board, RESULT)
            self.assertEqual(first.sequence, 1)
            time.sleep(.03)
            board.sendto(packets[-1], peer)  # emulate a lost first result at the board
            second, _ = receive_kind(board, RESULT)
            self.assertEqual(second, first)
            self.assertEqual(detector.calls, 1)
        finally: receiver.close(); board.close()
    def test_peer_pinning_and_idempotent_command_ack(self):
        core, video = BoardCore(ROOT / "tests/board_core.dll"), MockVideo()
        service = Service(core, video, "127.0.0.1", 0)
        target = service.socket.getsockname()
        one = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); one.bind(("127.0.0.1", 0)); one.settimeout(.05)
        other = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            one.sendto(encode(HELLO, 0, 0, 0, struct.pack("!I", 123)), target)
            time.sleep(.002); service.pump()
            status, _ = receive_kind(one, STATUS); session = status.session
            other.sendto(encode(HELLO, 0, 0, 0, struct.pack("!I", 456)), target)
            time.sleep(.002); service.pump()
            self.assertEqual(service.nonce, 123)
            for _ in range(2):
                one.sendto(encode(COMMAND, session, 1, 0, b"r"), target)
                time.sleep(.002); service.pump()
                ack, _ = receive_kind(one, STATUS)
                self.assertEqual(json.loads(ack.payload)["cmdok"], 1)
            self.assertEqual(video.clears, 2)  # handshake + one reset; duplicate didn't execute twice
        finally: service.close(); one.close(); other.close()

class CleanupTests(unittest.TestCase):
    def test_tk_rgb_preview_smoke(self):
        import tkinter as tk
        root = tk.Tk(); root.withdraw()
        try:
            pixels = np.zeros((2, 3, 3), np.uint8); pixels[0, 0] = [9, 17, 23]
            photo = tk.PhotoImage(master=root, data=b"P6\n3 2\n255\n" + pixels.tobytes(), format="PPM")
            self.assertEqual(photo.get(0, 0), (9, 17, 23))
            self.assertEqual((photo.width(), photo.height()), (3, 2))
        finally: root.destroy()
    def test_snapshot_owns_plain_array_and_invalidates_before_copy(self):
        from video import Video
        log = []
        class Buffer(np.ndarray):
            def invalidate(self): log.append("invalidate")
        class Lib:
            def linux_snapshot_index(self): return 1
        b = np.full((2, 3, 3), 5, np.uint8).view(Buffer)
        v = Video.__new__(Video); v.lib = Lib(); v.buffers = [None] * 4 + [b]
        result = v.snapshot()
        self.assertIs(type(result), np.ndarray)
        b.fill(99)
        self.assertEqual(int(result[0, 0, 0]), 5)
        self.assertEqual(log, ["invalidate"])
    def test_dma_halt_precedes_free_and_failed_reset_retains_buffers(self):
        from video import Video
        log = []
        class Lib:
            def linux_hw_close(self): log.append("halt"); return 0
        class Overlay:
            fail = False
            def download(self):
                log.append("reset-pl")
                if self.fail: raise RuntimeError("reset failed")
        class Buffer:
            def freebuffer(self): log.append("free")
        v = Video.__new__(Video); v.lib = Lib(); v.overlay = Overlay(); v.opened = True; v.buffers = [Buffer()]
        v.overlay.fail = True
        with self.assertRaises(RuntimeError): v.close()
        self.assertEqual(log, ["halt", "reset-pl"])
        self.assertEqual(len(v.buffers), 1)
        v.overlay.fail = False; v.close()
        self.assertEqual(log[-3:], ["halt", "reset-pl", "free"])

if __name__ == "__main__": unittest.main(verbosity=2)

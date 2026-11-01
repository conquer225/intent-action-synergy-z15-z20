"""A single owner handles the UDP epoch, reassembly, native detector and commands."""
import ctypes as C
from collections import deque
import hashlib
import json
import queue
import secrets
import socket
import struct
import threading
import time
from pathlib import Path
from net_protocol import (HELLO, FRAME, RESULT, COMMAND, STATUS, Reassembler,
                          encode, decode, unpack_result, FRAME_DEADLINE, newer,
                          decode_image, validate_metadata, validate_status)
ROOT = Path(__file__).resolve().parents[1]
class NativeDetector:
    def __init__(self, library=None):
        path = Path(library) if library else ROOT / "pc_runtime/pupil.dll"
        if library is None:
            manifest = json.loads((ROOT / "pc_runtime/pupil_manifest.json").read_text(encoding="utf-8"))
            if manifest["abi"] != 1 or hashlib.sha256(path.read_bytes()).hexdigest() != manifest["dll_sha256"]:
                raise RuntimeError("pupil.dll 与构建记录不匹配")
            for name, digest in manifest["sources"].items():
                if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != digest:
                    raise RuntimeError("检测源码已改动，需要重建 pupil.dll：" + name)
        self.lib = C.CDLL(str(path))
        self.lib.pc_infer.argtypes = [C.c_void_p, C.c_uint32, C.c_void_p, C.c_void_p]
        self.lib.pc_infer.restype = C.c_int
        self.lib.pc_protocol_version.restype = C.c_uint
        if self.lib.pc_protocol_version() != 1:
            raise RuntimeError("pupil runtime ABI")
    def infer(self, frame):
        data = frame.image
        if frame.fields[20] & 4:
            data = decode_image(frame).tobytes()
        output = C.create_string_buffer(80)
        started = time.monotonic()
        if not self.lib.pc_infer(data, len(data), frame.metadata, output):
            raise ValueError("native inference input")
        result = bytearray(output.raw)
        struct.pack_into("!I", result, 72, round((time.monotonic() - started) * 1000))
        return bytes(result)
class Receiver(threading.Thread):
    def __init__(self, board="192.168.1.10", port=5001, bind="0.0.0.0", local_port=5001, detector=None):
        super().__init__(daemon=True, name="Z15-pupil-receiver")
        self.target = (socket.gethostbyname(board), int(port))
        self.bind = (bind, int(local_port))
        self.detector = detector
        self.stop_event = threading.Event()
        self.updates = queue.Queue(maxsize=2)
        self.commands = queue.Queue(maxsize=8)
        self.session = 0
        self.nonce = secrets.randbits(32) or 1
        self.frames = self.bad_packets = self.late_frames = 0
        self.command_seq = 0
        self.pending = None
        self.status_sequence = None
        self.last_status = 0
        self.state = {}
        self.last_control = None
        self.socket = None
    def post(self, item):
        if self.last_control is not None:
            item["last_control"] = self.last_control
        if self.updates.full():
            try:
                self.updates.get_nowait()
            except queue.Empty:
                pass
        self.updates.put_nowait(item)
    def command(self, code):
        if code not in "crt" or len(code) != 1:
            raise ValueError("command")
        self.commands.put_nowait(code)
    def close(self):
        self.stop_event.set()
        self.join(timeout=2)
    def run(self):
        reassembly = Reassembler()
        cached = None
        retired = deque(maxlen=8)
        last_hello = 0
        try:
            if self.detector is None:
                self.detector = NativeDetector()
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            if hasattr(socket, "SIO_UDP_CONNRESET"):
                self.socket.ioctl(socket.SIO_UDP_CONNRESET, False)
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4 * 1024 * 1024)
            self.socket.bind(self.bind)
            self.socket.settimeout(0.02)
            self.post(dict(message=f"等待板卡 {self.target[0]}:{self.target[1]}，本机端口 {self.socket.getsockname()[1]}"))
            while not self.stop_event.is_set():
                now = time.monotonic()
                if now - last_hello >= 0.5:
                    self.socket.sendto(encode(HELLO, 0, 0, 0, struct.pack("!I", self.nonce)), self.target)
                    last_hello = now
                if self.last_status and now - self.last_status > 1.5:
                    self.session = 0
                    self.status_sequence = None
                    self.last_status = 0
                    self.state = {}
                    self.pending = None
                    cached = None
                    while not self.commands.empty():
                        self.commands.get_nowait()
                    reassembly.reset()
                    self.post(dict(message="板端状态超时；眼控已暂停，等待重新连接", disconnected=True))
                if self.session and self.pending is None:
                    try:
                        cmd = self.commands.get_nowait()
                    except queue.Empty:
                        cmd = None
                    if cmd:
                        self.command_seq = (self.command_seq + 1) & 0xffffffff or 1
                        self.pending = dict(code=cmd, sequence=self.command_seq, started=now, sent=0)
                if self.pending and now - self.pending["sent"] >= 0.15:
                    if now - self.pending["started"] > 1.2:
                        self.post(dict(message="控制请求未收到板端回执，请重试"))
                        self.pending = None
                    else:
                        self.socket.sendto(encode(COMMAND, self.session, self.pending["sequence"], 0,
                                                  self.pending["code"].encode("ascii")), self.target)
                        self.pending["sent"] = now
                try:
                    data, peer = self.socket.recvfrom(1201)
                except (socket.timeout, ConnectionResetError):
                    continue
                if peer != self.target:
                    continue
                try:
                    packet = decode(data)
                    if packet.kind == STATUS:
                        state = json.loads(packet.payload)
                        validate_status(state, self.nonce)
                        if not packet.session or packet.session in retired:
                            continue
                        if packet.session != self.session:
                            if self.session:
                                retired.append(self.session)
                            self.session = packet.session
                            self.status_sequence = None
                            reassembly.reset()
                            self.pending = None
                            cached = None
                            while not self.commands.empty():
                                self.commands.get_nowait()
                            self.post(dict(message="会话已建立；看 HDMI 白点进行三点校准"))
                        if self.status_sequence is not None and not newer(packet.sequence, self.status_sequence):
                            continue
                        self.status_sequence = packet.sequence
                        self.last_status = time.monotonic()
                        self.state = state
                        if self.pending and state.get("cmdseq") == self.pending["sequence"]:
                            self.last_control = dict(session=self.session, sequence=self.pending["sequence"],
                                                     code=self.pending["code"], accepted=bool(state.get("cmdok")))
                            self.post(dict(message="板端已接受控制" if state.get("cmdok") else "板端拒绝控制：双眼、时效或校准状态不满足"))
                            self.pending = None
                        self.post(dict(status=state, received=self.last_status))
                    elif packet.kind == FRAME and packet.session == self.session:
                        validate_metadata(packet.payload)
                        key = (packet.session, packet.sequence, packet.sampled_ms)
                        instant = time.monotonic()
                        if cached and cached[0] == key:
                            if cached[1] != packet.payload[:52]:
                                raise ValueError("conflicting completed-frame metadata")
                            if instant - cached[3] < FRAME_DEADLINE and instant - cached[4] >= 0.025:
                                self.socket.sendto(cached[2], self.target)
                                cached[4] = instant
                            continue
                        frame = reassembly.push(packet, time.monotonic())
                        if frame is None:
                            continue
                        result = self.detector.infer(frame)
                        if time.monotonic() - frame.received >= FRAME_DEADLINE:
                            self.late_frames += 1
                            self.post(dict(message="电脑处理/组帧超过 220 ms，本帧未回传"))
                            continue
                        response = encode(RESULT, self.session, packet.sequence, packet.sampled_ms, result)
                        self.socket.sendto(response, self.target)
                        cached = [key, packet.payload[:52], response, frame.received, time.monotonic()]
                        self.frames += 1
                        self.post(dict(frame=frame, result=unpack_result(result), frames=self.frames,
                                       dropped=reassembly.dropped, bad=self.bad_packets, received=time.monotonic()))
                except (ValueError, KeyError, struct.error, UnicodeError, RecursionError):
                    self.bad_packets += 1
        except Exception as exc:
            self.post(dict(error=f"{type(exc).__name__}: {exc}"))
        finally:
            if self.socket is not None:
                self.socket.close()

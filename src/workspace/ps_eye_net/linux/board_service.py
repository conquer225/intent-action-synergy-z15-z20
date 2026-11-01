"""USB-WiFi/Linux transport for the exact r8-derived eye controller and live video."""
import argparse
import json
import logging
import secrets
import socket
import struct
import sys
import time
import zlib
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from board_core import BoardCore
from net_protocol import (HELLO, FRAME, RESULT, COMMAND, STATUS, META, CHUNK, FRAME_DEADLINE,
                          encode, decode, newer)
def now_ms():
    return int(time.monotonic() * 1000) & 0xffffffff
def chunks(meta, pixels, session, sequence, sampled, jpeg=True):
    fields = list(META.unpack(meta))
    if jpeg:
        import cv2
        import numpy as np
        iw, ih = fields[4:6]
        image = np.frombuffer(pixels, dtype=np.uint8).reshape(ih, iw, 3)
        ok, data = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 95])
        if not ok:
            raise RuntimeError("face JPEG encoding failed")
        pixels = data.tobytes()
        fields[20] |= 4
    fields[21] = len(pixels)
    fields[22] = zlib.crc32(pixels)
    fields[25] = (len(pixels) + CHUNK - 1) // CHUNK
    packets = []
    for i in range(fields[25]):
        fields[23:25] = [i * CHUNK, i]
        payload = META.pack(*fields) + pixels[i * CHUNK:(i + 1) * CHUNK]
        packets.append(encode(FRAME, session, sequence, sampled, payload))
    return packets
class Service:
    def __init__(self, core, video, bind="0.0.0.0", port=5001, interface=None, jpeg=True):
        self.core, self.video = core, video
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        if hasattr(socket, "SIO_UDP_CONNRESET"):
            self.socket.ioctl(socket.SIO_UDP_CONNRESET, False)  # host loopback parity
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4 * 1024 * 1024)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 1024 * 1024)
        if interface:
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_BINDTODEVICE, interface.encode() + b"\0")
        self.socket.bind((bind, port))
        self.socket.setblocking(False)
        self.peer = None
        self.session = self.nonce = 0
        self.peer_time = self.status_time = 0.0
        self.sequence = self.status_seq = self.cmd_seq = self.cmd_ok = 0
        self.failures = 0
        self.cooldown_until = 0.0
        self.jpeg = jpeg
        self.event_seq = 0
        self.probing = False
    def send_status(self):
        if self.peer is None:
            return
        state = self.core.state()
        if hasattr(self.video, "counters"):
            state.update(self.video.counters())
        state.update(nonce=self.nonce, cmdseq=self.cmd_seq, cmdok=self.cmd_ok)
        self.status_seq = (self.status_seq + 1) & 0xffffffff
        self.socket.sendto(encode(STATUS, self.session, self.status_seq, now_ms(),
                                  json.dumps(state, separators=(",", ":")).encode("ascii")), self.peer)
        self.status_time = time.monotonic()
    def pump(self):
        # A finite batch prevents a UDP flood from starving frame/timeout handling.
        for _ in range(64):
            try:
                data, peer = self.socket.recvfrom(1201)
            except BlockingIOError:
                break
            except ConnectionResetError:
                continue
            try:
                p = decode(data)
            except ValueError:
                continue
            if p.kind == HELLO and p.session == 0 and len(p.payload) == 4:
                nonce = struct.unpack("!I", p.payload)[0]
                if not nonce:
                    continue
                live = self.peer is not None and time.monotonic() - self.peer_time < 1.5
                if live and (peer != self.peer or nonce != self.nonce):
                    continue
                if not live:
                    self.peer, self.nonce = peer, nonce
                    self.session = secrets.randbits(32) or 1
                    self.cmd_seq = self.cmd_ok = 0
                    self.cooldown_until = 0
                    self.failures = 0
                    self.core.reset()
                    self.video.clear()
                    logging.info("NET_PEER %s session=%08x; calibration cleared", peer, self.session)
                self.peer_time = time.monotonic()
                self.send_status()
                continue
            if peer != self.peer or p.session != self.session or time.monotonic() - self.peer_time >= 1.5:
                continue
            if p.kind == RESULT:
                accepted = self.core.lib.board_probe_packet(data, len(data), now_ms()) if self.probing else self.core.accept(data, now_ms())
                if accepted and not self.probing:
                    self.send_status()
            elif p.kind == COMMAND and len(p.payload) == 1 and p.sequence:
                if p.sequence == self.cmd_seq:
                    self.send_status()
                elif not self.cmd_seq or newer(p.sequence, self.cmd_seq):
                    self.cmd_seq = p.sequence
                    code = chr(p.payload[0])
                    self.cmd_ok = int(code in "crt" and self.core.command(code, now_ms()))
                    logging.info("CONTROL code=%r seq=%s accepted=%s", code, self.cmd_seq, self.cmd_ok)
                    if self.cmd_ok:
                        self.video.clear()
                    self.send_status()
    def step(self):
        self.pump()
        current = time.monotonic()
        if self.peer and current - self.peer_time >= 1.5:
            self.peer = None
            self.core.reset()
            self.video.clear()
            logging.warning("Wi-Fi/PC lease expired; local PS fallback")
        desired = self.peer is not None and current >= self.cooldown_until
        local = self.core.state()["source"] == "LOCAL"
        self.probing = bool(desired and local and self.cooldown_until)
        source = desired and not self.probing
        if not self.probing and self.core.source(source):
            self.video.clear()
            logging.info("SOURCE %s; recalibration required", "PC" if source else "LOCAL")
        image = self.video.snapshot()
        sampled = now_ms()
        self.sequence = (self.sequence + 1) & 0xffffffff
        if source or self.probing:
            accepted = self.core.state()["accepted"]
            meta, pixels = self.core.prepare(image, sampled, self.sequence, self.session, probe=self.probing)
            waiting = self.core.lib.board_probe_waiting if self.probing else self.core.lib.board_waiting
            timeout = self.core.lib.board_probe_timeout if self.probing else self.core.timeout
            packets = chunks(meta, pixels, self.session, self.sequence, sampled, self.jpeg)
            for i, packet in enumerate(packets):
                self.socket.sendto(packet, self.peer)
                if i % 8 == 7:
                    self.pump()
                    time.sleep(0.0005)
                if not waiting():
                    break
            resent = False
            while waiting():
                self.pump()
                age = ((now_ms() - sampled) & 0xffffffff)
                if not resent and age >= 100:
                    # One bounded resend repairs missing image fragments/result loss.
                    for i, packet in enumerate(packets):
                        if self.peer is None:
                            break
                        self.socket.sendto(packet, self.peer)
                        if i % 8 == 7:
                            self.pump()
                            time.sleep(0.0005)
                        if not waiting():
                            break
                    resent = True
                if timeout(now_ms()):
                    break
                time.sleep(0.0005)
            if self.probing:
                if self.core.lib.board_probe_promote(now_ms()):
                    self.failures = 0
                    self.cooldown_until = 0
                    logging.info("PC probe accepted; source switched, recalibration required")
                else:
                    self.cooldown_until = time.monotonic() + 2
                    self.core.lib.board_pause()
                    logging.warning("PC probe failed; retained LOCAL source and calibration")
                self.probing = False
            elif self.core.state()["accepted"] != accepted:
                self.failures = 0
            else:
                self.failures += 1
                if self.failures >= 3:
                    self.cooldown_until = time.monotonic() + 2
                    self.failures = 0
                    logging.warning("PC results missing/stale; local PS fallback, retry in 2 s")
        else:
            self.core.local(image, sampled, self.sequence)
        state = self.core.state()
        if state["commit"] and state["event"] != self.event_seq:
            self.event_seq = state["event"]
            logging.info("EYE_EVENT seq=%s direction=%s source=%s", state["event"], state["dir"], state["source"])
            self.send_status()
            self.core.lib.board_event_consumed()
        self.video.publish(self.sequence, sampled)
        if self.peer and time.monotonic() - self.status_time >= 0.5:
            self.send_status()
        self.pump()
    def close(self):
        self.core.reset()
        try:
            self.video.close()
        finally:
            self.socket.close()
def wireless_interface():
    candidates = [p.name for p in Path("/sys/class/net").iterdir() if (p / "wireless").exists()]
    if len(candidates) != 1:
        raise RuntimeError("Specify --interface: detected wireless interfaces " + repr(candidates))
    return candidates[0]
def interface_ipv4(name):
    import fcntl
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        data = fcntl.ioctl(s.fileno(), 0x8915, struct.pack("256s", name.encode()[:15]))
        return socket.inet_ntoa(data[20:24])
def main():
    p = argparse.ArgumentParser()
    p.add_argument("--interface", help="已连接 Wi-Fi 的接口，例如 wlan0；不自动改 Wi-Fi 密码/网络设置")
    p.add_argument("--port", type=int, default=5001)
    p.add_argument("--raw", action="store_true", help="BGR 原像素传输，带宽高于默认 JPEG95")
    args = p.parse_args()
    import signal
    def stop(signum, frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, stop)
    import fcntl
    from video import Video, verify_runtime
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", stream=sys.stdout)
    lock = open("/run/z15-eye-wifi.lock", "w")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    interface = args.interface or wireless_interface()
    if not (Path("/sys/class/net") / interface / "wireless").exists():
        raise RuntimeError("Selected interface is not a wireless interface: " + interface)
    ip = interface_ipv4(interface)
    library = verify_runtime()
    core = BoardCore(library)
    video = Video(core)
    service = None
    try:
        service = Service(core, video, bind=ip, port=args.port, interface=interface, jpeg=not args.raw)
        logging.info("Z15_EYE_WIFI_READY interface=%s ip=%s port=%s codec=%s", interface, ip, args.port, "BGR" if args.raw else "JPEG95")
        while True:
            service.step()
    except KeyboardInterrupt:
        logging.info("Stopping eye control")
    finally:
        if service:
            service.close()
        else:
            video.close()
        lock.close()
if __name__ == "__main__":
    main()

"""Private, bounded MP4 upload and memory-only decode check. No PL access."""
import argparse
import hashlib
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import threading
import time
from urllib.parse import unquote, urlsplit
import uuid
import zlib

MAX_FILE = 512 * 1024 * 1024
MAX_STORE = 2 * 1024 * 1024 * 1024
BLOCK = 256 * 1024


def file_sha(path):
    digest=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):digest.update(block)
    return digest.hexdigest()


def write_json(path, value):
    part = path.with_suffix(".json.part")
    part.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    part.replace(path)


class Store:
    def __init__(self, root, key, decoder):
        self.root = Path(root)
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.key, self.decoder = key, str(decoder)
        self.upload_lock = threading.Lock()
        self.decode_lock = threading.Lock()
        self.state_lock = threading.Lock()

    def available(self, length):
        used = sum(path.stat().st_size for path in self.root.iterdir() if path.is_file())
        return used + length <= MAX_STORE and shutil.disk_usage(self.root).free >= length + 1024 ** 3

    def items(self):
        with self.state_lock:
            return [json.loads(path.read_text(encoding="utf-8")) for path in sorted(self.root.glob("*.json"))]

    def decode(self, item):
        with self.decode_lock:
            path = self.root / (item["id"] + ".mp4")
            worker = Path(__file__).with_name("decode_worker.py")
            with self.state_lock:
                item["decode_state"] = "running"
                write_json(self.root / (item["id"] + ".json"), item)
            try:
                result = subprocess.run([sys.executable, str(worker), self.decoder, str(path)],
                                        capture_output=True, text=True, timeout=27)
            except subprocess.TimeoutExpired:
                item.update(decode_state="failed", decode_error="解码测试超过27秒，已停止；文件保留。")
            else:
                if result.returncode:
                    item.update(decode_state="failed", decode_error="解码测试未通过（退出码%d）；文件保留。" % result.returncode)
                else:
                    try:
                        report = json.loads(result.stdout)
                    except ValueError:
                        item.update(decode_state="failed", decode_error="解码器未返回有效结果。")
                    else:
                        allowed = {"width", "height", "frames", "complete", "decoded_fps", "wall_s", "peak_rss_mib", "process_cpu_percent", "codec_profile"}
                        item.update(decode_state="passed" if report.get("frames", 0) > 0 else "failed",
                                    decode={k: v for k, v in report.items() if k in allowed},
                                    hdmi_verified=False)
            with self.state_lock:
                write_json(self.root / (item["id"] + ".json"), item)
            print(json.dumps({"event": "decode_finished", "id": item["id"],
                              "state": item["decode_state"], "hdmi_verified": False}), flush=True)


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def setup(self):
        super().setup()
        self.connection.settimeout(15)

    def log_message(self, *_):
        pass

    def reply(self, status, value, content_type="application/json"):
        data = value if isinstance(value, bytes) else json.dumps(value, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(data)

    def reject(self, status, message):
        self.close_connection = True
        self.reply(status, {"error": message})

    def authorized(self):
        if not hmac.compare_digest(self.headers.get("X-Media-Key", "").encode(), self.server.store.key.encode()):
            self.reject(403, "请使用本轮带访问码的上传链接。")
            return False
        origin = self.headers.get("Origin")
        if origin and urlsplit(origin).netloc != self.headers.get("Host"):
            self.reject(403, "不接受其他网页发起的上传。")
            return False
        return True

    def do_GET(self):
        if self.path == "/":
            self.reply(200, Path(__file__).with_name("upload.html").read_bytes(), "text/html; charset=utf-8")
        elif self.path == "/health":
            self.reply(200, {"upload_ready": True, "scope": "private file upload", "hdmi_verified": False})
        elif self.path == "/status" and self.authorized():
            self.reply(200, {"files": self.server.store.items(), "hdmi_verified": False})
        elif self.path != "/status":
            self.reject(404, "页面不存在。")

    def do_POST(self):
        if not self.authorized():
            return
        if self.path != "/upload":
            self.reject(404, "接口不存在。")
            return
        if self.headers.get("Transfer-Encoding"):
            self.reject(400, "上传必须提供文件长度。")
            return
        name = unquote(self.headers.get("X-File-Name", ""))
        crc_expected = self.headers.get("X-File-CRC32", "").lower()
        raw_length = self.headers.get("Content-Length", "")
        if (not raw_length.isdecimal() or not re.fullmatch(r"[0-9a-f]{8}", crc_expected)
                or not name.lower().endswith(".mp4") or len(name) > 200
                or any(character in name for character in ("/", "\\", "\x00", "\r", "\n"))):
            self.reject(400, "请选择普通MP4文件；文件名或校验信息不合格。")
            return
        length = int(raw_length)
        if not 12 <= length <= MAX_FILE:
            self.reject(413, "第一轮请选择不超过512MB的MP4。")
            return
        store = self.server.store
        if not store.upload_lock.acquire(blocking=False):
            self.reject(409, "另一项上传仍在进行，请稍后重试。")
            return
        try:
            if not store.available(length):
                self.reject(507, "本轮空间配额不足；不会删除原文件。")
                return
            identifier = uuid.uuid4().hex
            part = store.root / (identifier + ".mp4.part")
            digest, crc, received = hashlib.sha256(), 0, 0
            started = time.monotonic()
            try:
                with part.open("xb") as handle:
                    while received < length:
                        data = self.rfile.read(min(BLOCK, length - received))
                        if not data:
                            raise ConnectionError("上传连接提前关闭。")
                        if received == 0 and (len(data) < 12 or data[4:8] != b"ftyp"):
                            self.reject(415, "文件头不是当前支持的普通MP4；未发布。")
                            return
                        handle.write(data)
                        digest.update(data)
                        crc = zlib.crc32(data, crc)
                        received += len(data)
                    handle.flush()
                    import os
                    os.fsync(handle.fileno())
            except (TimeoutError, ConnectionError, OSError):
                self.close_connection = True
                print(json.dumps({"event": "incomplete_upload", "id": identifier, "bytes": received}), flush=True)
                return
            if "%08x" % (crc & 0xffffffff) != crc_expected:
                self.reject(422, "手机与板端校验码不一致；文件隔离保留，未发布。")
                return
            item = {"id": identifier, "name": name, "bytes": received,
                    "crc32": crc_expected, "sha256": digest.hexdigest(), "integrity": "passed",
                    "upload_seconds": round(time.monotonic() - started, 3), "decode_state": "queued",
                    "hdmi_verified": False}
            with store.state_lock:
                part.replace(store.root / (identifier + ".mp4"))
                write_json(store.root / (identifier + ".json"), item)
            threading.Thread(target=store.decode, args=(item.copy(),), daemon=True).start()
            self.reply(201, item)
            print(json.dumps({"event": "upload_verified", "id": identifier, "bytes": received}), flush=True)
        finally:
            store.upload_lock.release()


def make_server(bind, port, store):
    server = ThreadingHTTPServer((bind, port), Handler)
    server.store = store
    server.daemon_threads = True
    return server


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bind", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=9117)
    parser.add_argument("--store", type=Path, required=True)
    parser.add_argument("--key-file", type=Path, required=True)
    parser.add_argument("--decoder", type=Path, required=True)
    args = parser.parse_args()
    import os
    os.umask(0o077)
    store = Store(args.store, args.key_file.read_text().strip(), args.decoder)
    with make_server(args.bind, args.port, store) as server:
        print("PRIVATE_MP4_UPLOAD_READY", flush=True)
        server.serve_forever(poll_interval=.5)

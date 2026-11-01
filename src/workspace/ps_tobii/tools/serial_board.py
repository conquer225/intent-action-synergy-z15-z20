"""Local serial console deployment; stdin JSON describes trusted operator commands."""
import base64
import gzip
import hashlib
import json
from pathlib import Path
import re
import shlex
import sys
import time
import uuid

import serial


class Board:
    def __init__(self, port="COM23"):
        self.s = serial.Serial(port=None, baudrate=115200, timeout=0.1, write_timeout=5)
        self.s.dtr = False
        self.s.rts = False
        self.s.port = port
        self.s.open()
        self.s.write(b"\r")
        self._prompt(3)
        self.s.write(b"stty -echo\r")
        self._prompt(3)

    def _prompt(self, timeout):
        end = time.monotonic() + timeout
        data = bytearray()
        while time.monotonic() < end:
            data.extend(self.s.read(max(1, self.s.in_waiting)))
            if re.search(rb"xilinx@pynq:[^\r\n]*\$ $", data):
                return bytes(data)
        raise TimeoutError("Expected board shell prompt; received " + repr(bytes(data[-1000:])))

    def run(self, command, timeout=15):
        token = "__Z15_DONE_" + uuid.uuid4().hex + "__"
        wrapped = "sh -c " + shlex.quote(command) + "; printf '\\n" + token + ":%s\\n' \"$?\"\r"
        if any(len(line.encode()) > 3000 for line in wrapped.splitlines()):
            raise ValueError("Console line too long; upload a script instead")
        data = bytearray()
        # Bound writes so large compressed overlays do not hit write_timeout.
        wire = wrapped.encode()
        for offset in range(0, len(wire), 2048):
            self.s.write(wire[offset:offset + 2048])
            if self.s.in_waiting:
                data.extend(self.s.read(self.s.in_waiting))
        end = time.monotonic() + timeout
        pattern = re.compile(rb"\r?\n" + token.encode() + rb":(\d+)\r?\n")
        while time.monotonic() < end:
            data.extend(self.s.read(max(1, self.s.in_waiting)))
            if len(data) > 16 * 1024 * 1024:
                raise RuntimeError("Console output exceeded 16 MiB")
            match = pattern.search(data)
            if match:
                output = bytes(data[:match.start()]).decode("utf-8", "replace").replace("\r\n", "\n")
                self._prompt(2) if not re.search(rb"xilinx@pynq:[^\r\n]*\$ $", data[match.end():]) else None
                return {"command": command, "exit_code": int(match[1]), "output": output}
        self.s.write(b"\x03")
        try:
            self._prompt(3)
        except TimeoutError:
            pass
        raise TimeoutError("Board command timed out; partial output: " + bytes(data[-4000:]).decode("utf-8", "replace"))

    def upload(self, local, remote):
        content = Path(local).read_bytes()
        encoded = base64.b64encode(gzip.compress(content)).decode()
        tag = "Z15_UPLOAD_" + uuid.uuid4().hex
        part = remote + ".part"
        packed = part + ".gz"
        result = self.run(": > " + shlex.quote(packed))
        if result["exit_code"]:
            raise RuntimeError("Cannot open upload destination: " + result["output"])
        # sh -c itself has Linux's per-argument size limit; never pass the
        # entire base64 overlay as a single shell argument.
        for offset in range(0, len(encoded), 32768):
            chunk = encoded[offset:offset + 32768]
            prefix = "base64 -d <<'" + tag + "' >> " + shlex.quote(packed) + "\n"
            command = prefix + "\n".join(chunk[i:i+768] for i in range(0, len(chunk), 768)) + "\n" + tag
            result = self.run(command, 20)
            if result["exit_code"]:
                raise RuntimeError("Upload chunk failed: " + result["output"][-2000:])
        result = self.run("gzip -dc " + shlex.quote(packed) + " > " + shlex.quote(part), 20)
        if result["exit_code"]:
            raise RuntimeError("Upload decompression failed: " + result["output"])
        digest = hashlib.sha256(content).hexdigest()
        check = self.run("sha256sum " + shlex.quote(part))
        if not check["output"].startswith(digest + " "):
            raise RuntimeError("Uploaded file hash mismatch: " + repr(check))
        result = self.run("mv -- " + shlex.quote(part) + " " + shlex.quote(remote) + " && rm -- " + shlex.quote(packed))
        if result["exit_code"]:
            raise RuntimeError(result)
        return {"remote": remote, "bytes": len(content), "sha256": digest}

    def download(self, remote, local):
        # Preserve read errors instead of returning base64's successful pipe exit.
        script = "import base64,gzip,sys; from pathlib import Path; print(base64.b64encode(gzip.compress(Path(sys.argv[1]).read_bytes())).decode())"
        result = self.run("python3 -c " + shlex.quote(script) + " " + shlex.quote(remote), 60)
        if result["exit_code"]:
            raise RuntimeError(result)
        content = gzip.decompress(base64.b64decode(result["output"].strip(), validate=True))
        destination = Path(local)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
        return {"local": str(destination.resolve()), "bytes": len(content), "sha256": hashlib.sha256(content).hexdigest()}

    def close(self):
        try:
            self.s.write(b"stty echo\r")
            self._prompt(2)
        finally:
            self.s.close()


def main():
    request = json.load(sys.stdin)
    board = Board(request.get("port", "COM23"))
    try:
        for item in request["operations"]:
            op = item.get("op", "run")
            if op == "run":
                result = board.run(item["command"], item.get("timeout", 15))
                if item.get("save"):
                    destination = Path(item["save"])
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    destination.write_text(result["output"], encoding="utf-8")
                print(json.dumps(result, ensure_ascii=False), flush=True)
            elif op == "upload":
                print(json.dumps(board.upload(item["local"], item["remote"])), flush=True)
            elif op == "download":
                print(json.dumps(board.download(item["remote"], item["local"])), flush=True)
            else:
                raise ValueError("Unknown operation: " + op)
    finally:
        board.close()


if __name__ == "__main__":
    main()

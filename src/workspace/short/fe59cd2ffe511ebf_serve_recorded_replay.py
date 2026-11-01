"""One-run, allowlisted LAN transfer between this PC and the user's Z15."""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


def serve(root, bind, board_ip, port):
    root = root.resolve()
    offered = {
        "recorded_frames.bin": root / "recorded_cyton/recorded_frames.bin",
        "raw_uv.npy": root / "recorded_cyton/raw_uv.npy",
        "gldma_board_check_replay_arm": root / "gldma_board_check_replay_arm",
        "gldma_board_check_replay_arm_static": root / "gldma_board_check_replay_arm_static",
        "analyze_recorded_replay.py": Path(__file__).with_name("analyze_recorded_replay.py"),
    }
    received = {"pl_output.bin", "board_report.json", "board_run.log"}

    class Handler(BaseHTTPRequestHandler):
        def permitted(self):
            if self.client_address[0] != board_ip:
                self.send_error(403)
                return False
            return True

        def do_GET(self):
            if not self.permitted():
                return
            source = offered.get(self.path.removeprefix("/"))
            if source is None or not source.is_file():
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Length", str(source.stat().st_size))
            self.end_headers()
            with source.open("rb") as stream:
                while chunk := stream.read(65536):
                    self.wfile.write(chunk)

        def do_POST(self):
            if not self.permitted():
                return
            name = self.path.removeprefix("/")
            if name not in received:
                self.send_error(404)
                return
            try:
                length = int(self.headers.get("Content-Length", ""))
            except ValueError:
                length = 0
            if not 0 < length <= 10_000_000:
                self.send_error(413)
                return
            destination = root / name
            try:
                with destination.open("xb") as stream:
                    remaining = length
                    while remaining:
                        block = self.rfile.read(min(remaining, 65536))
                        if not block:
                            raise ConnectionError("Incomplete upload")
                        stream.write(block)
                        remaining -= len(block)
            except FileExistsError:
                self.send_error(409)
                return
            self.send_response(201)
            self.end_headers()
            self.wfile.write(b"stored\n")

    server = ThreadingHTTPServer((bind, port), Handler)
    print(f"REPLAY_TRANSFER_READY bind={bind}:{port} allowed_board={board_ip}", flush=True)
    try:
        server.serve_forever(poll_interval=0.2)
    finally:
        server.server_close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--bind", required=True)
    parser.add_argument("--board-ip", required=True)
    parser.add_argument("--port", type=int, default=9139)
    args = parser.parse_args()
    serve(args.root, args.bind, args.board_ip, args.port)

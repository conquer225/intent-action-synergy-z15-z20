#!/usr/bin/env python3
"""Minimal OpenBCI Cyton serial probe using only the Python standard library."""

import argparse
import array
import fcntl
import json
import os
import select
import termios
import time


def configure_serial(fd: int) -> None:
    attrs = termios.tcgetattr(fd)
    attrs[0] = 0
    attrs[1] = 0
    attrs[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
    attrs[3] = 0
    attrs[4] = termios.B115200
    attrs[5] = termios.B115200
    attrs[6][termios.VMIN] = 0
    attrs[6][termios.VTIME] = 0
    termios.tcsetattr(fd, termios.TCSANOW, attrs)
    termios.tcflush(fd, termios.TCIOFLUSH)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", default="/dev/ttyUSB0")
    parser.add_argument("--timeout", type=float, default=6.0)
    parser.add_argument("--query-only", action="store_true",
                        help="Query uppercase V instead of resetting Cyton with lowercase v")
    args = parser.parse_args()

    fd = os.open(args.port, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
    try:
        configure_serial(fd)
        os.write(fd, b"s")
        time.sleep(0.25)
        termios.tcflush(fd, termios.TCIFLUSH)
        command = b"V" if args.query_only else b"v"
        os.write(fd, command)

        deadline = time.monotonic() + args.timeout
        response = bytearray()
        while time.monotonic() < deadline:
            readable, _, _ = select.select([fd], [], [], 0.25)
            if not readable:
                continue
            chunk = os.read(fd, 4096)
            if chunk:
                response.extend(chunk)
                if b"$$$" in response:
                    break

        print(f"CYTON_PROBE_BYTES={len(response)}")
        print(response.decode("ascii", errors="replace"))
        if args.query_only:
            queued = array.array('i', [0])
            fcntl.ioctl(fd, termios.TIOCOUTQ, queued, True)
            print(json.dumps(dict(query="V", soft_reset=False,
                                  response_bytes=len(response), tx_queued_bytes=queued[0])))
        if b"$$$" in response:
            print("CYTON_SERIAL_HANDSHAKE_OK")
            return 0
        print("CYTON_SERIAL_HANDSHAKE_NO_RESPONSE")
        return 2
    finally:
        os.close(fd)


if __name__ == "__main__":
    raise SystemExit(main())

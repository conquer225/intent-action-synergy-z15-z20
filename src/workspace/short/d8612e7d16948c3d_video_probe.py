"""Inspect actual V4L2 formats and attempt one frame without pretending success."""
import errno
import fcntl
import json
import os
from pathlib import Path
import struct
import time

import cv2


def formats(device):
    fd = os.open(device, os.O_RDWR | os.O_NONBLOCK)
    result = []
    try:
        cap = bytearray(104)
        fcntl.ioctl(fd, 0x80685600, cap)
        print(json.dumps({"device": device, "capability_hex": cap.hex()}), flush=True)
        for index in range(32):
            desc = bytearray(64)
            struct.pack_into("II", desc, 0, index, 1)
            try:
                fcntl.ioctl(fd, 0xC0405602, desc)
            except OSError as exc:
                if exc.errno == errno.EINVAL:
                    break
                raise
            fourcc = struct.unpack_from("I", desc, 44)[0]
            item = {"index": index, "description": bytes(desc[12:44]).split(b"\0")[0].decode("ascii", "replace"),
                    "fourcc_hex": hex(fourcc), "fourcc": bytes(desc[44:48]).decode("ascii", "replace"), "sizes": []}
            for size_index in range(32):
                size = bytearray(44)
                struct.pack_into("II", size, 0, size_index, fourcc)
                try:
                    fcntl.ioctl(fd, 0xC02C564A, size)
                except OSError as exc:
                    if exc.errno == errno.EINVAL:
                        break
                    raise
                item["sizes"].append(struct.unpack_from("7I", size, 8))
            result.append(item)
    finally:
        os.close(fd)
    return result


print(json.dumps({"formats": formats("/dev/video0")}), flush=True)
start = time.monotonic()
cap = cv2.VideoCapture("/dev/video0", cv2.CAP_V4L2)
try:
    print(json.dumps({"opened": cap.isOpened(), "width": cap.get(cv2.CAP_PROP_FRAME_WIDTH),
                      "height": cap.get(cv2.CAP_PROP_FRAME_HEIGHT), "fourcc": cap.get(cv2.CAP_PROP_FOURCC)}), flush=True)
    if cap.isOpened():
        ok, frame = cap.read()
        result = {"read_ok": ok, "elapsed_s": time.monotonic() - start}
        if ok and frame is not None:
            path = Path("captures/uvc_first.png")
            result.update(shape=list(frame.shape), minimum=int(frame.min()), maximum=int(frame.max()),
                          mean=float(frame.mean()), saved=bool(cv2.imwrite(str(path), frame)), path=str(path))
        print(json.dumps(result), flush=True)
finally:
    cap.release()

"""Optional private-image smoke; never treats a still image as human calibration."""
import argparse
import json
import sys
import time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools")); sys.path.insert(0, str(ROOT / "linux"))
import cv2
import numpy as np
from board_core import BoardCore
from pc_receiver import NativeDetector
from net_protocol import FRAME, RESULT, Frame, Packet, Reassembler, decode, encode, unpack_result
from board_service import chunks
def replay(image_path, core_path, detector_path=None, jpeg=True, count=20):
    original = cv2.imread(str(image_path))
    if original is None: raise ValueError("Cannot load image")
    h, w = original.shape[:2]
    scale = min(1280 / w, 720 / h); ww, hh = round(w * scale), round(h * scale)
    image = np.full((720, 1280, 3), 160, np.uint8)
    x, y = (1280 - ww) // 2, (720 - hh) // 2
    image[y:y + hh, x:x + ww] = cv2.resize(original, (ww, hh), interpolation=cv2.INTER_NEAREST)
    core = BoardCore(core_path); core.source(1)
    detector = NativeDetector(detector_path)
    rows, calibrating = [], False
    for seq in range(1, count + 1):
        sampled = 1000 + seq * 100
        began = time.perf_counter()
        meta, pixels = core.prepare(image, sampled, seq, 123)
        frame = Frame(Packet(FRAME, 123, seq, sampled, b""), meta, pixels, time.monotonic())
        if jpeg:
            assembly = Reassembler()
            for data in chunks(meta, pixels, 123, seq, sampled, True):
                complete = assembly.push(decode(data), time.monotonic())
                if complete is not None: frame = complete
        result = detector.infer(frame)
        elapsed = round((time.perf_counter() - began) * 1000)
        accepted = core.accept(encode(RESULT, 123, seq, sampled, result), sampled + elapsed)
        eyes = unpack_result(result)
        state = core.state()
        rows.append(dict(pair=eyes["pair"], both=int(eyes["left"]["valid"] and eyes["right"]["valid"]), accepted=accepted,
                         crop=tuple(frame.fields[:6]), search=bool(frame.fields[20] & 1), elapsed_ms=elapsed,
                         nx=tuple(state["nx"]), stage=state["stage"]))
        if seq >= 3 and not calibrating:
            calibrating = core.command("c", sampled + elapsed)
    return dict(input_width=w, input_height=h, preprocessing="nearest resize and letterbox into1280x720 on host",
                codec="JPEG95" if jpeg else "raw BGR", frames=len(rows), faces=sum(r["pair"] for r in rows),
                both_eyes_valid=sum(r["both"] for r in rows), accepted=sum(r["accepted"] for r in rows),
                nonsearch_crop_windows=len({r["crop"] for r in rows if not r["search"]}),
                elapsed_ms_range=[min(r["elapsed_ms"] for r in rows), max(r["elapsed_ms"] for r in rows)],
                calibration_entered=calibrating, event_count=core.state()["event"],
                board_tested=False, accuracy_measured=False,
                limitations="Repeated historical image;100ms synthetic sample interval;no human gaze changes or wireless link")
def main():
    p = argparse.ArgumentParser()
    p.add_argument("--image", type=Path, required=True)
    p.add_argument("--core", type=Path, default=ROOT / "tests/board_core.dll")
    p.add_argument("--detector", type=Path)
    p.add_argument("--frames", type=int, default=20)
    p.add_argument("--raw", action="store_true")
    p.add_argument("--output", type=Path)
    args = p.parse_args()
    if not 1 <= args.frames <= 500: p.error("frames1..500")
    report = replay(args.image, args.core, args.detector, not args.raw, args.frames)
    text = json.dumps(report, indent=2)
    print(text)
    if args.output: args.output.write_text(text, encoding="utf-8")
if __name__ == "__main__": main()

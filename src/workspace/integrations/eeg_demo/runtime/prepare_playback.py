"""Finite board-only preparation; never loads PL or changes formal services."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

BASE = Path(__file__).resolve().parent
STATE = json.loads((BASE / "playback_state.json").read_text())


def main():
    source = Path(STATE["source"])
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    if before != STATE["source_sha256"]:
        raise RuntimeError("Uploaded file changed before conversion")
    report = {"original_sha256": before, "pc_runtime_required": False,
              "hdmi_tested": False, "audio_tested": False, "conversions": []}
    input_file = source
    for width, height in ((1280, 720), (640, 360)):
        temporary = BASE / ("video_%dx%d.partial.mp4" % (width, height))
        output = BASE / ("video_%dx%d.mp4" % (width, height))
        if output.exists() or temporary.exists():
            raise RuntimeError("Retained conversion already exists; inspect it instead of overwriting")
        result = subprocess.run([str(BASE / "transcode_video"), str(input_file),
            str(temporary), str(width), str(height), "20"],
            capture_output=True, text=True, timeout=240, check=True)
        converted = json.loads(result.stdout)
        if not converted["complete"] or converted["encoded_frames"] < 50:
            raise RuntimeError("Finite clip conversion did not cover the expected duration")
        with temporary.open("rb") as handle:
            import os
            os.fsync(handle.fileno())
        temporary.rename(output)
        converted.update(path=str(output), bytes=output.stat().st_size,
                         sha256=hashlib.sha256(output.read_bytes()).hexdigest())
        report["conversions"].append(converted)
        input_file = output if width == 1280 else input_file
        (BASE / "conversion_report.json").write_text(json.dumps(report, indent=2))
        print(json.dumps(converted), flush=True)
    report["original_preserved"] = hashlib.sha256(source.read_bytes()).hexdigest() == before
    report["completed_monotonic"] = time.monotonic()
    (BASE / "conversion_report.json").write_text(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

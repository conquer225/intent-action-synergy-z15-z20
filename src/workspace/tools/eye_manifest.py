"""Record or verify the paired eye-control HDL/XDC, bitstream and reports."""
import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "report/eye/build_manifest.json"


def digest(path, normalize=False):
    data = path.read_bytes()
    if normalize:
        data = data.replace(b"\r\n", b"\n")
    return hashlib.sha256(data).hexdigest()


def record():
    sources = sorted([*ROOT.glob("src/eye/*.sv"), *ROOT.glob("src/eye/*.v"),
                      *ROOT.glob("src/third_party/projectf/*.v"),
                      *ROOT.glob("board/constraints/*.xdc")])
    outputs = [ROOT / "report/eye" / name for name in
               ("z15_eye_top.bit", "timing.rpt", "utilization.rpt", "drc.rpt", "cdc.rpt", "clocks.rpt")]
    bit = outputs[0]
    if not bit.is_file() or bit.stat().st_size < 100000:
        raise SystemExit("Missing or invalid bitstream; build first")
    if any(p.stat().st_mtime > bit.stat().st_mtime for p in sources):
        raise SystemExit("HDL/XDC is newer than bitstream; rebuild before recording")
    data = {"recorded_utc": datetime.now(timezone.utc).isoformat(),
            "tool": "Vivado 2023.1", "part": "xc7z015clg485-2",
            "source_hash_normalization": "CRLF to LF; outputs use raw bytes",
            "physical_validation": "pending",
            "sources": {p.relative_to(ROOT).as_posix(): digest(p, normalize=True) for p in sources},
            "outputs": {p.relative_to(ROOT).as_posix(): digest(p) for p in outputs}}
    MANIFEST.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print("Recorded", len(sources), "design inputs and", len(outputs), "outputs")


def verify():
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    errors = []
    for name, expected in (data["sources"] | data["outputs"]).items():
        path = ROOT / name
        if not path.is_file() or digest(path, normalize=name in data["sources"]) != expected:
            errors.append(name)
    if errors:
        raise SystemExit("Hash mismatch or missing file: " + ", ".join(errors))
    print("PASS: HDL/XDC and bitstream/report hashes match build manifest")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--record", action="store_true", help="Only after a successful matching build")
    args = parser.parse_args()
    record() if args.record else verify()

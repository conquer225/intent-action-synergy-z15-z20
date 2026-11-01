"""Build the exact C localization/feature implementation with a byte protocol ABI."""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
INPUTS = ["src/app/auto_face.c", "src/app/auto_face.h", "src/app/haar.c", "src/app/haar.h",
          "src/app/eye_tracker.c", "src/app/eye_tracker.h", "src/app/net_protocol.c", "src/app/net_protocol.h",
          "src/app/face_model.inc", "src/app/face_alt_model.inc", "src/app/eye_model.inc",
          "tests/include/xil_types.h", "tools/pc_net_bridge.c"]
def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--gcc", default="C:/mingw64/mingw64/bin/gcc.exe")
    args = parser.parse_args()
    out = ROOT / "pc_runtime"
    out.mkdir(exist_ok=True)
    dll = out / "pupil.dll"
    subprocess.run([args.gcc, "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror", "-shared",
                    "-static", "-static-libgcc", "-Itests/include", "-Isrc/app",
                    "src/app/haar.c", "src/app/auto_face.c", "src/app/eye_tracker.c",
                    "src/app/net_protocol.c", "tools/pc_net_bridge.c", "-lm", "-o", str(dll)], cwd=ROOT, check=True)
    manifest = {"abi": 1, "dll_sha256": sha(dll), "sources": {f: sha(ROOT / f) for f in INPUTS}}
    (out / "pupil_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print("Built", dll)
if __name__ == "__main__":
    main()

"""Verify freshly extracted releases do not depend on the canonical checkout."""
import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
def main():
    p = argparse.ArgumentParser()
    p.add_argument("--full", type=Path, default=ROOT.parent.parent / "Z15_Eye_WiFi_r9.zip")
    p.add_argument("--pc", type=Path, default=ROOT.parent.parent / "Z15_Eye_WiFi_PC_r9.zip")
    args = p.parse_args()
    work = ROOT.parent / "local"
    work.mkdir(exist_ok=True)
    base = Path(tempfile.mkdtemp(prefix="wifi_release_check_", dir=work))
    for i, path in enumerate((args.full, args.pc)):
        with zipfile.ZipFile(path) as z:
            assert z.testzip() is None
            manifest = json.loads(z.read("ps_eye_net/report/package_manifest.json"))
            for name, digest in manifest.items(): assert hashlib.sha256(z.read("ps_eye_net/" + name)).hexdigest() == digest
            z.extractall(base / str(i))
    full, pc = base / "0/ps_eye_net", base / "1/ps_eye_net"
    subprocess.run([sys.executable, "tools/verify_release.py"], cwd=full, check=True)
    command = 'import sys;sys.path.insert(0,"tools");from pc_receiver import NativeDetector;assert NativeDetector().lib.pc_protocol_version()==1;print("PASS portable PC DLL and source import")'
    subprocess.run([sys.executable, "-c", command], cwd=pc, check=True)
    subprocess.run([sys.executable, "tools/net_monitor.py", "--help"], cwd=pc, check=True, stdout=subprocess.DEVNULL)
    assert not list(full.rglob("*.png")) and not list(full.rglob("*.jpg"))
    assert not list(full.rglob("*.xpr")) and not (full / "hardware/vitis_build").exists()
    print("PASS portable full/PC ZIP bytes, checked source manifests, native load and CLI; no private captures or workspaces")
    print("Inspection copies:", base.resolve())
if __name__ == "__main__": main()

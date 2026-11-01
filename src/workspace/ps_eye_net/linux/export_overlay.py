"""Export paired PYNQ files and the exact generated Vitis MMIO drivers."""
import hashlib
import json
import shutil
import zipfile
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    bsp = ROOT / "hardware/vitis_build/net_platform/ps7_cortexa9_0/standalone_domain/bsp/ps7_cortexa9_0/libsrc"
    if not bsp.exists(): raise RuntimeError("Generate fresh platform/BSP with build/build_hardware.ps1 first")
    sources = {"axivdma_v*": "xaxivdma", "gpiops_v*": "xgpiops", "vtc_v*": "xvtc"}
    for pattern, prefix in sources.items():
        folders = list(bsp.glob(pattern)); assert len(folders) == 1, pattern
        for old in (ROOT / "linux/driver").glob(prefix + "*.c"):
            source = folders[0] / "src" / old.name
            assert source.exists(), source
            shutil.copyfile(source, old)
        for old in (ROOT / "linux/include").glob(prefix + "*.h"):
            source = ROOT / "bsp/include" / old.name
            assert source.exists(), source
            shutil.copyfile(source, old)
    with zipfile.ZipFile(ROOT / "hardware/ps_eye_net.xsa") as z:
        hwh = z.read("system.hwh")
        names = [n for n in z.namelist() if n.endswith(".bit")]
        assert len(names) == 1
        bit = z.read(names[0])
        assert bit == (ROOT / "hardware/ps_eye_net.bit").read_bytes()
    (ROOT / "linux/overlay/eye_wifi.bit").write_bytes(bit)
    (ROOT / "linux/overlay/eye_wifi.hwh").write_bytes(hwh)
    files = [p for p in (ROOT / "hardware/source").rglob("*") if p.is_file()]
    files += [ROOT / "build" / name for name in ("create_hardware.tcl", "add_live_osd.tcl", "implement_hardware.tcl", "check_live_osd_timing.tcl")]
    artifacts = ("hardware/ps_eye_net.bit", "hardware/ps_eye_net.xsa", "hardware/fsbl.elf", "hardware/ps7_init.tcl",
                 "bsp/include/xparameters.h", "bsp/lib/libxil.a", "bsp/lib/liblwip4.a")
    manifest = dict(abi=1, sources={p.relative_to(ROOT).as_posix(): sha(p) for p in files},
                    artifacts={name: sha(ROOT / name) for name in artifacts})
    (ROOT / "report/hardware_build_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print("Exported paired overlay/driver configuration and hardware source identities; rebuild Linux runtime next")
if __name__ == "__main__": main()

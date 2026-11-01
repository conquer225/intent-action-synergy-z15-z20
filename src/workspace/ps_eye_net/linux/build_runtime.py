"""Cross-build Linux ARMv7 shared library; a native on-board gcc also works."""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
def main():
    p = argparse.ArgumentParser()
    p.add_argument("--gcc", default="D:/vivado/Vitis/2023.1/gnu/aarch32/nt/gcc-arm-linux-gnueabi/bin/arm-linux-gnueabihf-gcc.exe")
    args = p.parse_args()
    files = ["src/app/haar.c", "src/app/auto_face.c", "src/app/eye_tracker.c", "src/app/net_protocol.c",
             "src/app/net_control.c", "src/app/live_osd.c", "tools/board_bridge.c", "tools/pc_net_bridge.c",
             "src/app/emio_sccb_cfg/emio_sccb_cfg.c", "src/app/ov5640/ov5640_init.c",
             "src/app/display_ctrl_hdmi/display_ctrl_hdmi.c", "linux/hardware_linux.c", "linux/dma_shutdown.c"]
    files += [str(f.relative_to(ROOT)).replace("\\", "/") for f in sorted((ROOT / "linux/driver").glob("*.c"))]
    out = ROOT / "linux/runtime/libeye_board.so"
    subprocess.run([args.gcc, "-std=c11", "-D_POSIX_C_SOURCE=200809L", "-O2", "-g", "-Wall", "-Wextra", "-Werror", "-fPIC", "-shared",
                    "-mcpu=cortex-a9", "-mfpu=vfpv3", "-mfloat-abi=hard", "-Wl,--no-undefined",
                    "-Ilinux/include", "-Ibsp/include", "-Isrc/app", *files, "-lm", "-o", str(out)], cwd=ROOT, check=True)
    sources = files + ["linux/dma_shutdown.h"] + [str(f.relative_to(ROOT)).replace("\\", "/") for sub in ("linux/include", "src/app", "bsp/include")
                       for f in (ROOT / sub).rglob("*") if f.is_file() and f.suffix in (".h", ".inc")]
    manifest = dict(abi=1, target="ARMv7 Linux EABI hard-float", library_sha256=hashlib.sha256(out.read_bytes()).hexdigest(),
                    sources={f: hashlib.sha256((ROOT / f).read_bytes()).hexdigest() for f in sources})
    (ROOT / "linux/runtime/manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print("Built", out)
if __name__ == "__main__":
    main()

"""Build display-only ARM library against the existing r9 drivers."""
import hashlib
import json
from pathlib import Path
import subprocess
ROOT = Path(__file__).resolve().parents[2]
T = ROOT / "ps_tobii"
R9 = ROOT / "ps_eye_net"
sources = [T / "src/display.c", R9 / "linux/dma_shutdown.c",
           R9 / "src/app/display_ctrl_hdmi/display_ctrl_hdmi.c"]
sources += sorted((R9 / "linux/driver").glob("xaxivdma*.c"))
sources += sorted((R9 / "linux/driver").glob("xvtc*.c"))
out = T / "build/libtobii_display.so"
out.parent.mkdir(exist_ok=True)
gcc = "D:/vivado/Vitis/2023.1/gnu/aarch32/nt/gcc-arm-linux-gnueabi/bin/arm-linux-gnueabihf-gcc.exe"
subprocess.run([gcc, "-std=c11", "-D_POSIX_C_SOURCE=200809L", "-O2", "-g", "-Wall", "-Wextra", "-Werror",
                "-fPIC", "-shared", "-mcpu=cortex-a9", "-mfpu=vfpv3", "-mfloat-abi=hard", "-Wl,--no-undefined",
                *["-I" + str(R9 / p) for p in ("linux/include", "bsp/include", "src/app", "linux")],
                *map(str, sources), "-o", str(out)], check=True)
manifest = {"library_sha256": hashlib.sha256(out.read_bytes()).hexdigest(),
            "sources": {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},
            "overlay": {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                        for p in (R9 / "linux/overlay").glob("eye_wifi.*")}}
(T / "build/display_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
print(out)

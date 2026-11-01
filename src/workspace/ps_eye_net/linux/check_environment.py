"""Read-only board preflight; optional CMA reservation probe never starts DMA."""
import argparse
import ctypes
import importlib
import json
import os
import platform
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

def check(interface=None, probe_cma=False):
    report = dict(kernel=platform.release(), machine=platform.machine(), python=sys.version,
                  pointer_bits=ctypes.sizeof(ctypes.c_void_p) * 8, checks=[], wireless=[], usb=[])
    def record(name, ok, detail):
        report["checks"].append(dict(name=name, ok=bool(ok), detail=str(detail)))
    record("ARMv7 Linux", sys.platform.startswith("linux") and platform.machine() in ("armv7l", "armv8l")
           and report["pointer_bits"] == 32 and sys.byteorder == "little", platform.platform())
    record("root for /dev/mem and interface binding", hasattr(os, "geteuid") and os.geteuid() == 0, "Run with sudo")
    for name in ("numpy", "cv2", "pynq"):
        try:
            m = importlib.import_module(name)
            record(name, True, getattr(m, "__version__", getattr(m, "__file__", "available")))
        except Exception as exc:
            record(name, False, repr(exc))
    try:
        from video import verify_runtime
        path = verify_runtime()
        record("source/runtime identity", True, path)
        if sys.platform.startswith("linux"):
            lib = ctypes.CDLL(str(path)); lib.board_init()
            record("ARM library ABI / glibc", True, path.name)
    except Exception as exc:
        record("ARM library ABI / source identity", False, repr(exc))
    try:
        from pynq import Overlay
        overlay = Overlay(str(ROOT / "linux/overlay/eye_wifi.bit"), download=False)
        expected = {"axi_vdma_0": 0x43000000, "axi_vdma_1": 0x43010000,
                    "live_osd_0": 0x43c00000, "v_tc_0": 0x43c10000}
        addresses = {name: overlay.ip_dict.get(name, {}).get("phys_addr") for name in expected}
        record("PYNQ HWH parsing / register map (no download)", addresses == expected, addresses)
    except Exception as exc:
        record("PYNQ HWH parsing (no download)", False, repr(exc))
    try:
        from board_service import interface_ipv4
        candidates = [p for p in Path("/sys/class/net").iterdir() if (p / "wireless").exists()]
        for p in candidates:
            try: ip = interface_ipv4(p.name)
            except OSError: ip = None
            report["wireless"].append(dict(interface=p.name, ipv4=ip,
                driver=str((p / "device/driver").resolve()), state=(p / "operstate").read_text().strip()))
        selected = [w for w in report["wireless"] if w["interface"] == interface] if interface else report["wireless"]
        record("connected wireless IPv4", len(selected) == 1 and selected[0]["ipv4"] is not None
               and selected[0]["state"] == "up", selected)
    except Exception as exc:
        record("wireless interface", False, repr(exc))
    for p in Path("/proc/device-tree").glob("**/usb@*/dr_mode"):
        report["usb"].append(dict(node=str(p.parent), dr_mode=p.read_bytes().rstrip(b"\0").decode("ascii", "replace")))
    record("USB host device tree", any(u["dr_mode"] == "host" for u in report["usb"]), report["usb"])
    memory = Path("/proc/meminfo")
    report["memory"] = {line.split(":")[0]: line.split(":", 1)[1].strip() for line in memory.read_text().splitlines()
                        if line.startswith(("MemTotal:", "MemAvailable:", "CmaTotal:", "CmaFree:"))} if memory.exists() else {}
    record("/dev/mem", Path("/dev/mem").exists(), "/dev/mem")
    conflicts = []
    for device in Path("/sys/bus/platform/devices").glob("*"):
        if not (device / "driver").exists() or not (device / "resource").exists():
            continue
        try:
            for line in (device / "resource").read_text().splitlines():
                start, end, flags = [int(x, 16) for x in line.split()]
                if any(start <= b and end >= a for a, b in ((0x43000000, 0x4301ffff), (0x43c00000, 0x43c1ffff))):
                    conflicts.append(dict(device=device.name, driver=str((device / "driver").resolve())))
        except (OSError, ValueError):
            pass
    record("exclusive video registers", not conflicts, conflicts)
    if probe_cma:
        buffers = []
        try:
            from pynq import allocate
            import numpy as np
            for _ in range(5):
                b = allocate(shape=(720, 1280, 3), dtype=np.uint8)
                buffers.append(b)
                if not 0 < b.physical_address <= 0x40000000 - b.nbytes or b.physical_address % 8:
                    raise RuntimeError("CMA physical range/alignment")
            record("five CMA video buffers", True, [hex(b.physical_address) for b in buffers])
        except Exception as exc:
            record("five CMA video buffers", False, repr(exc))
        finally:
            for b in buffers: b.freebuffer()
    report["ready"] = all(c["ok"] for c in report["checks"])
    return report

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--interface")
    p.add_argument("--probe-cma", action="store_true")
    p.add_argument("--report", type=Path)
    args = p.parse_args()
    report = check(args.interface, args.probe_cma)
    text = json.dumps(report, indent=2, ensure_ascii=False)
    print(text)
    if args.report: args.report.write_text(text, encoding="utf-8")
    return 0 if report["ready"] else 1
if __name__ == "__main__": sys.exit(main())

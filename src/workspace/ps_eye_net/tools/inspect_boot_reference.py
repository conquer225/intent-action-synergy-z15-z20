"""Parse supplied U-Boot/FIT/FDT bytes without running any boot script."""
import hashlib
import json
import struct
import zlib
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]

def fdt(data):
    words = struct.unpack_from("!10I", data)
    magic, total, structure, strings = words[:4]
    assert magic == 0xd00dfeed and total <= len(data)
    names = data[strings:strings + words[8]]
    end = structure + words[9]
    pos, stack, nodes = structure, [], {}
    while pos < end:
        token = struct.unpack_from("!I", data, pos)[0]; pos += 4
        if token == 1:
            stop = data.index(0, pos)
            stack.append(data[pos:stop].decode("ascii")); pos = (stop + 4) & ~3
            nodes["/" + "/".join(stack[1:])] = {}
        elif token == 2: stack.pop()
        elif token == 3:
            length, offset = struct.unpack_from("!II", data, pos); pos += 8
            stop = names.index(0, offset)
            name = names[offset:stop].decode("ascii")
            nodes["/" + "/".join(stack[1:])][name] = data[pos:pos + length]
            pos = (pos + length + 3) & ~3
        elif token == 4: pass
        elif token == 9: break
        else: raise ValueError("FDT token")
    return nodes

def text(value): return value.rstrip(b"\0").decode("ascii", "replace")
def main():
    folder = ROOT / "linux/boot_reference"
    fit = fdt((folder / "image.ub").read_bytes())
    payloads = [(path, props["data"]) for path, props in fit.items() if path.startswith("/images/") and "data" in props]
    kernels = [data for path, data in payloads if text(fit[path].get("type", b"")) == "kernel"]
    dtbs = [data for path, data in payloads if text(fit[path].get("type", b"")) == "flat_dt"]
    assert len(kernels) == len(dtbs) == 1
    dt = fdt(dtbs[0])
    usb = {path: {name: text(props[name]) for name in ("status", "dr_mode", "compatible") if name in props}
           for path, props in dt.items() if "usb@" in path and "dr_mode" in props}
    assert any(u.get("dr_mode") == "host" and u.get("status") == "okay" for u in usb.values())
    hash_checks = []
    for path, data in payloads:
        for key, props in fit.items():
            if key.startswith(path + "/") and "value" in props and "algo" in props:
                algo = text(props["algo"])
                digest = struct.pack("!I", zlib.crc32(data)) if algo == "crc32" else hashlib.new(algo, data).digest()
                assert props["value"] == digest
                hash_checks.append(dict(node=key, algorithm=algo))
    assert len(hash_checks) >= 2
    script = (folder / "boot.scr").read_bytes()
    h = struct.unpack_from("!7I4B32s", script)
    assert h[0] == 0x27051956
    cleaned = script[:4] + bytes(4) + script[8:64]
    assert zlib.crc32(cleaned) == h[1] and zlib.crc32(script[64:64 + h[3]]) == h[6]
    report = dict(kernel_bytes=len(kernels[0]), kernel_sha256=hashlib.sha256(kernels[0]).hexdigest(),
                  usb=usb, bootargs=text(dt.get("/chosen", {}).get("bootargs", b"")),
                  memory={k: p.get("reg", b"").hex() for k, p in dt.items() if k.startswith("/memory")},
                  fit_hash_checks=hash_checks, boot_scr_crc="header and payload match", reference_only=True,
                  rootfs_included=False, wlan_driver_observed=False)
    (ROOT / "report/boot_reference_analysis.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("PASS working reference: USB host, FIT payload hashes and boot.scr CRC; no rootfs/WLAN driver claim")
if __name__ == "__main__": main()

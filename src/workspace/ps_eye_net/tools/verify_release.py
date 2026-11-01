"""Audit exported hardware, Linux/WLAN reference, native ABI and spare BOOT payloads."""
import hashlib
import json
import re
import struct
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def word(data, offset): return struct.unpack_from("<I", data, offset)[0]
def elf(path):
    data = path.read_bytes()
    assert data[:6] == b"\x7fELF\x01\x01" and struct.unpack_from("<H", data, 18)[0] == 40
    start, size, count = word(data, 28), struct.unpack_from("<H", data, 42)[0], struct.unpack_from("<H", data, 44)[0]
    segments = []
    for i in range(count):
        typ, off, va, pa, filesz, memsz, flags, align = struct.unpack_from("<8I", data, start + i * size)
        if typ == 1: segments.append(dict(address=pa, filesz=filesz, memsz=memsz, data=data[off:off + filesz]))
    return word(data, 24), segments
def manifest_check(folder, name, artifact, digest_key):
    manifest = json.loads((ROOT / folder / name).read_text(encoding="utf-8"))
    assert manifest["abi"] == 1 and sha(ROOT / artifact) == manifest[digest_key], artifact
    for path, digest in manifest["sources"].items():
        assert sha(ROOT / path) == digest, "Rebuild stale runtime: " + path
    return len(manifest["sources"])
def main():
    hardware = json.loads((ROOT / "report/hardware_build_manifest.json").read_text())
    for path, digest in {**hardware["sources"], **hardware["artifacts"]}.items():
        assert sha(ROOT / path) == digest, "Stale hardware export/source: " + path
    boot = (ROOT / "build/BOOT.BIN").read_bytes()
    assert word(boot, 0x20) == 0xaa995566 and word(boot, 0x24) == 0x584c4e58
    pht = word(boot, 0x9c)
    parts = []
    for i in range(3):
        h = pht + i * 64
        parts.append(dict(load=word(boot, h + 12), entry=word(boot, h + 16), attr=word(boot, h + 24),
                          offset=word(boot, h + 20) * 4, length=word(boot, h + 4) * 4))
    assert [p["attr"] & 0x30 for p in parts] == [0x10, 0x20, 0x10]
    memory = []
    for index, path in ((0, ROOT / "hardware/fsbl.elf"), (2, ROOT / "build/ps_eye_net.elf")):
        entry, segments = elf(path)
        assert entry == parts[index]["entry"]
        for s in segments:
            off = parts[index]["offset"] + s["address"] - parts[index]["load"]
            assert boot[off:off + s["filesz"]] == s["data"], path.name
            if index == 2:
                assert s["address"] >= 0x100000 and s["address"] + s["memsz"] <= 0x1000000
                memory.append(dict(start=hex(s["address"]), end=hex(s["address"] + s["memsz"])))
    assert parts[2]["entry"] == 0x100000
    bit = (ROOT / "hardware/ps_eye_net.bit").read_bytes()
    sync = bit.index(bytes.fromhex("aa995566"))
    payload = boot[parts[1]["offset"]:parts[1]["offset"] + parts[1]["length"]]
    swapped = b"".join(payload[i:i + 4][::-1] for i in range(0, len(payload), 4))
    assert bit[sync:] in swapped
    with zipfile.ZipFile(ROOT / "hardware/ps_eye_net.xsa") as z:
        bits = [n for n in z.namelist() if n.endswith(".bit")]
        assert len(bits) == 1 and z.read(bits[0]) == bit
        assert z.read("system.hwh") == (ROOT / "linux/overlay/eye_wifi.hwh").read_bytes()
        assert z.read("ps7_init.tcl") == (ROOT / "hardware/ps7_init.tcl").read_bytes()
        hwh = ET.fromstring(z.read("system.hwh"))
    assert (ROOT / "linux/overlay/eye_wifi.bit").read_bytes() == bit
    modules = {m.get("INSTANCE"): {p.get("NAME"): p.get("VALUE") for p in m.findall("./PARAMETERS/PARAMETER")}
               for m in hwh.findall(".//MODULE")}
    expected = {
        "axi_vdma_0": dict(C_BASEADDR=0x43000000, C_NUM_FSTORES=3, C_INCLUDE_MM2S=1, C_INCLUDE_S2MM=1,
                           C_INCLUDE_INTERNAL_GENLOCK=1, C_S2MM_GENLOCK_MODE=2, C_MM2S_GENLOCK_MODE=3,
                           C_S_AXIS_S2MM_TDATA_WIDTH=24, C_M_AXIS_MM2S_TDATA_WIDTH=24),
        "axi_vdma_1": dict(C_BASEADDR=0x43010000, C_NUM_FSTORES=2, C_INCLUDE_MM2S=0, C_INCLUDE_S2MM=1,
                           C_INCLUDE_INTERNAL_GENLOCK=0, C_S2MM_GENLOCK_MODE=0, C_S_AXIS_S2MM_TDATA_WIDTH=24),
        "live_osd_0": dict(C_BASEADDR=0x43c00000, WIDTH=1280, HEIGHT=720, PIXEL_HZ=75000000)}
    for name, settings in expected.items():
        for key, value in settings.items(): assert int(modules[name][key], 0) == value, (name, key)
    ps = modules["processing_system7_0"]
    assert ps["PCW_GPIO_EMIO_GPIO_ENABLE"] == "1" and ps["PCW_SD0_PERIPHERAL_ENABLE"] == "1"
    assert ps["PCW_ENET0_PERIPHERAL_ENABLE"] == "1" and "16" in ps["PCW_ENET0_ENET0_IO"]
    header = (ROOT / "bsp/include/xparameters.h").read_text()
    for key, value in {"XPAR_AXIVDMA_0_BASEADDR": 0x43000000, "XPAR_AXIVDMA_1_BASEADDR": 0x43010000,
                       "XPAR_AXIVDMA_0_NUM_FSTORES": 3, "XPAR_AXIVDMA_1_NUM_FSTORES": 2,
                       "XPAR_LIVE_OSD_0_BASEADDR": 0x43c00000}.items():
        m = re.search(r"^#define\s+" + key + r"\s+(\w+)", header, re.M)
        assert m and int(m[1].rstrip("UuLl"), 0) == value, key
    timing = (ROOT / "report/timing_summary.txt").read_text()
    assert "All user specified timing constraints are met." in timing and "unconstrained_internal_endpoints (0)" in timing
    summary = re.search(r"^\s+([\d.]+)\s+0\.000\s+0\s+\d+\s+([\d.]+)\s+0\.000\s+0\s+\d+", timing, re.M)
    assert summary and all(float(v) > 0 for v in summary.groups())
    skew = (ROOT / "report/bus_skew.txt").read_text()
    slacks = [float(x) for x in re.findall(r"Slack \(MET\) :\s+([0-9.]+)ns", skew)]
    assert slacks and "VIOLATED" not in skew
    assert b"r9-face-roi" in (ROOT / "build/ps_eye_net.elf").read_bytes()
    pc_sources = manifest_check("pc_runtime", "pupil_manifest.json", "pc_runtime/pupil.dll", "dll_sha256")
    linux_sources = manifest_check("linux/runtime", "manifest.json", "linux/runtime/libeye_board.so", "library_sha256")
    so = (ROOT / "linux/runtime/libeye_board.so").read_bytes()
    elf(ROOT / "linux/runtime/libeye_board.so")
    assert struct.unpack_from("<H", so, 16)[0] == 3 and word(so, 36) & 0x400
    versions = sorted({v.decode() for v in re.findall(rb"GLIBC_\d+\.\d+(?:\.\d+)?", so)})
    assert versions and max(tuple(map(int, v[6:].split("."))) for v in versions) <= (2, 17)
    reference = json.loads((ROOT / "report/wireless_reference.json").read_text())
    for p in (ROOT / "linux/boot_reference").iterdir():
        if p.name in reference["files"]: assert sha(p) == reference["files"][p.name]["sha256"]
    assert sha(ROOT / "linux/boot_reference/BOOT.BIN") != sha(ROOT / "build/BOOT.BIN")
    baseline = json.loads((ROOT / "report/r8_baseline.json").read_text())
    previous = ROOT.parent / "ps_eye_auto"
    old_check = "Not present in portable release; preserved hashes supplied"
    if previous.exists():
        for path, digest in baseline.items(): assert sha(previous / path) == digest, "r8 modified: " + path
        old_check = str(len(baseline)) + " original r8 files unchanged"
    for model, inc in (("frontalface_default", "face_model"), ("frontalface_alt", "face_alt_model"), ("eye", "eye_model")):
        assert sha(ROOT / "model" / ("haarcascade_" + model + ".xml")) in (ROOT / "src/app" / (inc + ".inc")).read_text()
    files = ("build/BOOT.BIN", "build/ps_eye_net.elf", "hardware/ps_eye_net.bit", "hardware/ps_eye_net.xsa",
             "hardware/fsbl.elf", "hardware/ps7_init.tcl", "bsp/lib/libxil.a", "bsp/lib/liblwip4.a",
             "linux/runtime/libeye_board.so", "linux/overlay/eye_wifi.bit", "linux/overlay/eye_wifi.hwh",
             "pc_runtime/pupil.dll", "linux/boot_reference/BOOT.BIN", "linux/boot_reference/image.ub")
    report = dict(version="r9-eye-wifi", board_tested=False, primary_transport="USB Wi-Fi via existing PYNQ/Linux",
                  rootfs_included=False, hwh_contract=expected, wns_ns=float(summary[1]), whs_ns=float(summary[2]),
                  minimum_bus_skew_slack_ns=min(slacks), bus_skew_paths=len(slacks), spare_boot_partitions=parts,
                  spare_app_memory=memory, pc_manifest_sources=pc_sources, linux_manifest_sources=linux_sources,
                  hardware_manifest_sources=len(hardware["sources"]),
                  linux_glibc_versions=versions, r8_baseline=old_check,
                  cdc_review="Inherited r8 held-data/req-ack contract; raw DRC/CDC/methodology reports retained",
                  sha256={name: sha(ROOT / name) for name in files})
    (ROOT / "report/release_verification.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("PASS paired bit/HWH/XSA/BSP, Linux ARM ABI, PC/ARM source identity, timing and spare boot payloads")
    print(old_check)
    return report
if __name__ == "__main__": main()

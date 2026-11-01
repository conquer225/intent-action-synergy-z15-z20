"""Check a trusted Vivado .bit/.hwh manifest without loading an overlay."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import sys
import xml.etree.ElementTree as ET


class CheckFailed(ValueError):
    """Well-formed artifacts disagree with the declared contract."""


def normalize_part(value):
    if not isinstance(value, str) or not re.fullmatch(r"(?:xc)?[a-z0-9]+", value.lower()):
        raise ValueError("part must include device and package, without a speed-grade suffix")
    return value.lower()[2:] if value.lower().startswith("xc") else value.lower()


def bit_part(data):
    """Read the device/package field from a complete tagged Vivado bit header."""
    if data[:13] != bytes.fromhex("00090ff00ff00ff00ff0000001"):
        raise ValueError("unsupported or truncated Vivado .bit header")
    offset, part = 13, None
    for expected in b"abcde":
        if offset >= len(data) or data[offset] != expected:
            raise ValueError("missing or out-of-order .bit field")
        offset += 1
        width = 4 if expected == ord("e") else 2
        if offset+width > len(data):
            raise ValueError("truncated .bit field length")
        length = int.from_bytes(data[offset:offset+width], "big")
        offset += width
        if length == 0 or offset+length > len(data):
            raise ValueError("truncated or empty .bit field")
        if expected == ord("b"):
            part = normalize_part(data[offset:offset+length].rstrip(b"\0").decode("ascii"))
        if expected == ord("e"):
            if length % 4 or offset+length != len(data):
                raise ValueError("invalid .bit payload size")
            return part
        offset += length
    raise ValueError("missing .bit payload")


def read_artifact(root, entry, suffix):
    if (not isinstance(entry, dict) or not isinstance(entry.get("path"), str)
            or not isinstance(entry.get("sha256"), str)
            or not re.fullmatch("[0-9a-fA-F]{64}", entry["sha256"])):
        raise ValueError("artifact needs a relative path and a 64-digit SHA256")
    relative = Path(entry["path"])
    if relative.is_absolute():
        raise ValueError("artifact paths must be relative to the manifest")
    path = (root/relative).resolve()
    try:
        path.relative_to(root)
    except ValueError:
        raise ValueError("artifact path escapes the manifest directory")
    if path.suffix.lower() != suffix:
        raise ValueError("expected a "+suffix+" artifact")
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != entry["sha256"].lower():
        raise CheckFailed("SHA256 mismatch: "+relative.as_posix())
    return path, data


def check(manifest_path, actual_part):
    path = Path(manifest_path).resolve()
    manifest = json.loads(path.read_text(encoding="utf-8-sig"))
    if (not isinstance(manifest, dict) or type(manifest.get("schema_version")) is not int
            or manifest["schema_version"] != 1
            or not isinstance(manifest.get("build_id"), str) or not manifest["build_id"].strip()):
        raise ValueError("expected schema_version=1 and a nonempty build_id")
    target = normalize_part(manifest.get("target_part"))
    if target != normalize_part(actual_part):
        raise CheckFailed("manifest part differs from the supplied physical part")
    bit_path, bit = read_artifact(path.parent, manifest.get("bit"), ".bit")
    hwh_path, hwh = read_artifact(path.parent, manifest.get("hwh"), ".hwh")
    if bit_path.stem != hwh_path.stem or bit_path.parent != hwh_path.parent:
        raise CheckFailed("PYNQ bit/hwh must have the same stem and directory")
    part = bit_part(bit)
    if part != target:
        raise CheckFailed("bit part "+str(part)+" differs from expected "+target)
    tree = ET.fromstring(hwh)
    system_info = [e for e in tree.iter() if e.tag.split("}")[-1] == "SYSTEMINFO"]
    if len(system_info) != 1:
        raise ValueError("HWH must contain one SYSTEMINFO with DEVICE and PACKAGE")
    device, package = system_info[0].get("DEVICE"), system_info[0].get("PACKAGE")
    if not device or not package:
        raise ValueError("HWH SYSTEMINFO lacks DEVICE or PACKAGE")
    hwh_part = normalize_part(device+package)
    if hwh_part != target:
        raise CheckFailed("HWH part "+hwh_part+" differs from expected "+target)
    ips = set()
    for element in tree.iter():
        if element.tag.split("}")[-1] == "MODULE":
            name = element.get("FULLNAME") or element.get("INSTANCE")
            if name:
                ips.add(name.strip("/"))
    required = manifest.get("required_ips")
    if (not isinstance(required, list) or not required
            or any(not isinstance(name, str) or not name.strip("/") for name in required)):
        raise ValueError("required_ips must list the IP instance paths used by this application")
    missing = sorted(set(name.strip("/") for name in required)-ips)
    if missing:
        raise CheckFailed("HWH missing required IP: "+", ".join(missing))
    return dict(passed=True, scope="offline_artifact_identity", board_executed=False,
                build_id=manifest["build_id"], bit_part=part, hwh_part=hwh_part,
                checked_files=[manifest["bit"]["path"], manifest["hwh"]["path"]],
                required_ips=required)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--part", required=True, help="device/package from the actual board record; no speed grade")
    args = parser.parse_args()
    try:
        report, code = check(args.manifest, args.part), 0
    except (OSError, ValueError, ET.ParseError, struct.error) as exc:
        code = 1 if isinstance(exc, CheckFailed) else 2
        report = dict(passed=False, scope="offline_artifact_identity", board_executed=False,
                      error=str(exc))
    print(json.dumps(report, ensure_ascii=True, indent=2))
    return code


if __name__ == "__main__":
    sys.exit(main())

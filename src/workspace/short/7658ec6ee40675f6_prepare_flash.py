"""Validate the COM17 application and preserve the original slot; no hardware access."""
import hashlib
import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
BACKUP_SHA = "bc674ab657020c455ea239e2862ce88366c049ceff39e6a81809801f53831013"
APP_OFFSET = 0x10000
APP_CAPACITY = 0x330000


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build-folder", default="arduino_ble_mouse")
    parser.add_argument("--manifest-name", default="com17_ble_mouse_preflash_20261006.json")
    args = parser.parse_args()
    if not args.build_folder.replace("_", "").isalnum() or Path(args.manifest_name).name != args.manifest_name:
        raise ValueError("Build folder and manifest must be simple names")
    backup_path = ROOT / "firmware_backups/com17_20261006_full_01.bin"
    app_path = ROOT / "build" / args.build_folder / "guardianloop_eye_mouse.ino.bin"
    partitions_path = app_path.with_name("guardianloop_eye_mouse.ino.partitions.bin")
    original = backup_path.read_bytes()
    application = app_path.read_bytes()
    partitions = partitions_path.read_bytes()
    if len(original) != 0x1000000 or sha(original) != BACKUP_SHA:
        raise ValueError("Original verified COM17 backup changed; no preparation")
    if not 24 < len(application) <= APP_CAPACITY:
        raise ValueError("Application does not fit original app0 partition")
    if application[0] != 0xE9 or application[12:14] != b"\x09\x00":
        raise ValueError("Not a valid ESP32-S3 image header")
    if application[2:4] != original[APP_OFFSET + 2:APP_OFFSET + 4]:
        raise ValueError("New app SPI mode/frequency/size does not match original header")
    if original[0x8000:0x8000 + len(partitions)] != partitions:
        raise ValueError("Generated partition layout differs from original backup")
    recovery = ROOT / "firmware_backups/com17_original_app0_0x10000_0x330000.bin"
    original_slot = original[APP_OFFSET:APP_OFFSET + APP_CAPACITY]
    if recovery.exists():
        if recovery.read_bytes() != original_slot:
            raise ValueError("Existing original slot backup changed")
    else:
        with recovery.open("xb") as stream:
            stream.write(original_slot)
    sources = sorted((ROOT / "firmware/guardianloop_eye_mouse").glob("*.ino"))
    sources += sorted((ROOT / "firmware/guardianloop_eye_mouse").glob("*.h"))
    manifest = {
        "device": {"port": "COM17", "usb_serial": "28:84:85:60:CD:9C", "chip": "esp32s3"},
        "application": {"path": str(app_path), "offset": APP_OFFSET, "capacity": APP_CAPACITY,
                        "bytes": len(application), "sha256": sha(application),
                        "spi_header_hex": application[2:4].hex()},
        "original_full_backup": {"path": str(backup_path), "sha256": BACKUP_SHA},
        "original_slot_recovery": {"path": str(recovery), "bytes": APP_CAPACITY,
                                   "sha256": sha(original[APP_OFFSET:APP_OFFSET + APP_CAPACITY])},
        "partition_binary_matches_backup": True,
        "original_bootloader_sha256_0_to_0x8000": sha(original[:0x8000]),
        "source_sha256": {str(path.relative_to(ROOT)): sha(path.read_bytes()) for path in sources},
        "writes_allowed_by_this_plan": ["application at 0x10000 only"],
        "bootloader_write_planned": False,
        "partition_write_planned": False,
        "full_chip_erase_planned": False,
        "recovery_writeback_tested": False,
    }
    result = ROOT / "output" / args.manifest_name
    with result.open("x", encoding="utf-8") as stream:
        json.dump(manifest, stream, indent=2)
        stream.write("\n")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()

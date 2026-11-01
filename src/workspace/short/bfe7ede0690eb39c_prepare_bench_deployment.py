"""Validate an app-only bench image and derive private recovery slices. No device IO."""
import argparse
import hashlib
import json
from pathlib import Path

from audit_firmware import audit, parse_image


BACKUP_SHA256 = "4b056926c447417ee6b9f1d36e461039dbcc261d011662a70d02a7f825a678a1"
APP_OFFSET = 0x10000
APP_SIZE = 0x100000


def save_slice(path, data):
    if path.exists():
        if path.read_bytes() != data:
            raise ValueError(f"Existing recovery file differs: {path.name}")
    else:
        with path.open("xb") as stream:
            stream.write(data)
    return {"path": str(path.resolve()), "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest()}


def prepare(app_path, backup_path, output_dir, *, motor_test=False):
    backup = backup_path.read_bytes()
    if len(backup) != 0x1000000 or hashlib.sha256(backup).hexdigest() != BACKUP_SHA256:
        raise ValueError("Current-device backup size or SHA-256 differs")
    backup_audit = audit(backup_path)
    tables = backup_audit["partition_tables"]
    if len(tables) != 1 or tables[0]["offset"] != 0x8000 or not tables[0]["md5_valid"]:
        raise ValueError("Unexpected current-device partition table")
    entries = tables[0]["entries"]
    expected = [("nvs", 1, 2, 0x9000, 0x6000),
                ("phy_init", 1, 1, 0xf000, 0x1000),
                ("factory", 0, 0, APP_OFFSET, APP_SIZE)]
    actual = [(p["name"], p["type"], p["subtype"], p["offset"], p["size"]) for p in entries]
    if actual != expected or any(p["flags"] for p in entries):
        raise ValueError("Unexpected current-device partitions or flags")
    data = app_path.read_bytes()
    image = parse_image(data, 0, len(data))
    if not image or image["chip_id"] != 9 or not image["checksum_valid"] or not image["appended_sha256_valid"]:
        raise ValueError("App is not a valid ESP32-S3 image")
    if image["image_size"] != len(data) or len(data) > APP_SIZE:
        raise ValueError("App does not fit the existing factory partition")
    if data[2:4] != backup[APP_OFFSET + 2:APP_OFFSET + 4]:
        raise ValueError("App flash mode/frequency/size header differs from current app")
    product = b"guardianloop-wheelchair-remote-0.1.0" if motor_test else b"guardianloop-wheelchair-bench-0.1.0"
    if product not in data:
        raise ValueError("Expected product identifier missing")
    output_dir.mkdir(parents=True, exist_ok=True)
    recovery = {
        "boot_and_table": save_slice(output_dir / "com16_boot_table_0_9000.bin", backup[:0x9000]),
        "factory": save_slice(output_dir / "com16_original_factory_10000_1m.bin",
                              backup[APP_OFFSET:APP_OFFSET + APP_SIZE]),
        "nvs_phy_factory": save_slice(output_dir / "com16_original_nvs_phy_factory_9000_107000.bin",
                                      backup[0x9000:APP_OFFSET + APP_SIZE]),
    }
    return {
        "app_path": str(app_path.resolve()), "app_bytes": len(data),
        "app_sha256": hashlib.sha256(data).hexdigest(),
        "app_offset": APP_OFFSET, "app_partition_bytes": APP_SIZE,
        "app_flash_header_matches_original": True,
        "app_flash_mode_frequency_size_header_hex": data[2:4].hex(),
        "app_image_checksums_valid": True,
        "motor_gpio_build": motor_test,
        "backup_sha256": BACKUP_SHA256, "recovery_files": recovery,
        "recovery_contains_private_nvs": True, "nvs_contents_inspected": False,
        "writeback_recovery_tested": False, "device_connected": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app", type=Path, required=True)
    parser.add_argument("--backup", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--motor-test", action="store_true")
    args = parser.parse_args()
    result = prepare(args.app, args.backup, args.output_dir, motor_test=args.motor_test)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    with args.report.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

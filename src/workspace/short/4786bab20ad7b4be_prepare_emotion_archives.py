"""Extract only EEG/metadata required for DEAP and SEED, without overwriting files."""

import json
import shutil
import zipfile
import zlib
from pathlib import Path


ROOT = Path(r"D:\ican\datasets")


def main():
    plans = [
        (ROOT / "DEAP/data_preprocessed_python.zip", ROOT / "DEAP",
         lambda name: name.startswith("data_preprocessed_python/") and name.endswith(".dat")),
        (ROOT / "SEED/SEED.zip", ROOT / "SEED",
         lambda name: name.startswith("SEED/Preprocessed_EEG/") and not name.endswith("/")),
    ]
    manifest = []
    for archive, destination, select in plans:
        with zipfile.ZipFile(archive) as source:
            members = [item for item in source.infolist() if select(item.filename)]
            required = sum(item.file_size for item in members
                           if not (destination / item.filename).exists())
            if shutil.disk_usage(destination).free < required + 5_000_000_000:
                raise RuntimeError(f"Insufficient space with 5 GB reserve: {archive}")
            for item in members:
                target = (destination / item.filename).resolve()
                if destination.resolve() not in target.parents:
                    raise ValueError(f"Unsafe archive path: {item.filename}")
                if target.exists():
                    checksum = 0
                    with target.open("rb") as stream:
                        for block in iter(lambda: stream.read(1024 * 1024), b""):
                            checksum = zlib.crc32(block, checksum)
                    if target.stat().st_size != item.file_size or checksum != item.CRC:
                        raise RuntimeError(f"Existing file differs; not overwritten: {target}")
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    partial = target.with_suffix(target.suffix + ".extracting")
                    with source.open(item) as incoming, partial.open("xb") as outgoing:
                        shutil.copyfileobj(incoming, outgoing, length=1024 * 1024)
                    partial.rename(target)
                manifest.append({"archive": str(archive), "file": str(target),
                                 "bytes": item.file_size, "zip_crc32": f"{item.CRC:08x}"})
                print(f"VERIFIED {target.name} ({item.file_size} bytes)", flush=True)
    output = Path(__file__).parent / "output/emotion_data_inventory/extracted_files.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"COMPLETE {len(manifest)} files: {output}")


if __name__ == "__main__":
    main()

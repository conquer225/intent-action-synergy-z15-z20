#!/usr/bin/env python3
"""Download only the PhysioNet left/right motor-imagery EDF runs, with SHA-256 checks."""

import argparse
import hashlib
import json
import os
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path


BASE = "https://physionet.org/files/eegmmidb/1.0.0"
S3_MIRROR = "https://physionet-open.s3.amazonaws.com/eegmmidb/1.0.0"
RUNS = (4, 8, 12)  # Imagined left/right fists. Runs 6/10/14 are BOTH fists vs feet.


def read_checksums(root):
    target = root / "SHA256SUMS.txt"
    if not target.is_file():
        with urllib.request.urlopen(BASE + "/SHA256SUMS.txt", timeout=60) as response:
            contents = response.read()
        target.write_bytes(contents)
    result = {}
    for line in target.read_text(encoding="utf-8").splitlines():
        digest, name = line.split(maxsplit=1)
        result[name.lstrip("*./")] = digest.lower()
    return result


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download_one(root, relative, expected, source_base):
    destination = root / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.is_file() and sha256_file(destination) == expected:
        return relative, "already_verified"
    if destination.is_file():
        # An existing incorrect/incomplete file is never used as data.
        raise ValueError(f"Checksum mismatch in existing file: {destination}")
    temporary = destination.with_suffix(destination.suffix + ".part")
    for attempt in range(3):
        try:
            request = urllib.request.Request(source_base + "/" + relative,
                                             headers={"User-Agent": "GuardianLoop-MI/1.0"})
            with urllib.request.urlopen(request, timeout=90) as response, temporary.open("wb") as output:
                for chunk in iter(lambda: response.read(1024 * 1024), b""):
                    output.write(chunk)
            actual = sha256_file(temporary)
            if actual != expected:
                raise ValueError(f"Downloaded SHA-256 mismatch: {relative}")
            os.replace(temporary, destination)
            return relative, "downloaded_verified"
        except (OSError, ValueError):
            temporary.unlink(missing_ok=True)
            if attempt == 2:
                raise
            time.sleep(1 + attempt)
    raise AssertionError("unreachable")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(r"D:\ican\datasets\EEGMMIDB"))
    parser.add_argument("--first", type=int, default=1)
    parser.add_argument("--last", type=int, default=109)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--source", choices=("physionet", "s3"), default="s3")
    args = parser.parse_args()
    if not 1 <= args.first <= args.last <= 109 or not 1 <= args.workers <= 12:
        parser.error("subjects must be 1..109, workers 1..12")
    args.root.mkdir(parents=True, exist_ok=True)
    source_base = S3_MIRROR if args.source == "s3" else BASE
    checksums = read_checksums(args.root)
    files = [f"S{subject:03d}/S{subject:03d}R{run:02d}.edf"
             for subject in range(args.first, args.last + 1) for run in RUNS]
    missing_hashes = [name for name in files if name not in checksums]
    if missing_hashes:
        raise ValueError(f"Official SHA-256 list missing {missing_hashes[:3]}")
    manifest = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(download_one, args.root, name, checksums[name], source_base): name
                   for name in files}
        for index, future in enumerate(as_completed(futures), 1):
            relative, state = future.result()
            manifest.append({"path": relative, "sha256": checksums[relative], "state": state})
            if index % 10 == 0 or index == len(files):
                print(f"verified {index}/{len(files)}", flush=True)
    manifest.sort(key=lambda item: item["path"])
    manifest_path = args.root / f"mi_download_manifest_{args.first:03d}_{args.last:03d}.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"COMPLETE: {manifest_path}", flush=True)


if __name__ == "__main__":
    main()

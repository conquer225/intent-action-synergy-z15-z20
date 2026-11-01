"""Download only MPD-DF raw EEG and annotations with checksum verification.

The published 50 EEG files are ~11.9 GB; PSG/video are not needed for the
fixed-montage EEG comparison. Existing verified files are reused. Partial
downloads remain in .part files for retry and are never treated as data.
"""

import argparse
import hashlib
import json
import shutil
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests


ARTICLE = "https://api.figshare.com/v2/articles/28455737"
DEFAULT_ROOT = Path(r"D:\ican\datasets\MPD-DF\raw_eeg")


def digest(path):
    md5 = hashlib.md5()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            md5.update(block)
    return md5.hexdigest()


def fetch(item, root):
    name = item["name"]
    target = root / name
    if target.is_file():
        if target.stat().st_size == item["size"] and digest(target) == item["computed_md5"]:
            return name, "verified-existing"
        raise RuntimeError(f"Existing target has wrong size/hash: {target}")
    partial = root / (name + ".part")
    for attempt in range(4):
        existing = partial.stat().st_size if partial.exists() else 0
        if existing > item["size"]:
            raise RuntimeError(f"Partial file exceeds declared size: {partial}")
        if existing == item["size"]:
            break
        headers = {"Range": f"bytes={existing}-"} if existing else {}
        # Figshare redirects to an S3 URL valid for only 10 seconds. A unique
        # query prevents an intermediate cache from replaying an expired link.
        url = item["download_url"] + f"?cb={time.time_ns()}-{attempt}"
        try:
            with requests.get(url, headers=headers, stream=True, timeout=(20, 120)) as response:
                response.raise_for_status()
                if existing and response.status_code != 206:
                    raise RuntimeError(f"Server refused resume for {name}; .part left intact")
                with partial.open("ab" if existing else "wb") as stream:
                    for block in response.iter_content(chunk_size=1024 * 1024):
                        if block:
                            stream.write(block)
        except (requests.RequestException, OSError):
            if attempt == 3:
                raise
            time.sleep(attempt + 1)
    if partial.stat().st_size != item["size"] or digest(partial) != item["computed_md5"]:
        raise RuntimeError(f"Downloaded checksum mismatch: {name}")
    partial.replace(target)
    return name, "verified-new"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--ids", nargs="*", default=None,
                        help="two-digit participant IDs; omitted means all 50")
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    if args.workers < 1 or args.workers > 8:
        raise SystemExit("Workers must be 1..8")
    args.root.mkdir(parents=True, exist_ok=True)
    article = requests.get(ARTICLE, timeout=30).json()
    full_items = [item for item in article["files"] if
                  item["name"].endswith("_EEG.edf") or item["name"].endswith("_Annotation.txt")]
    if len(full_items) != 100:
        raise RuntimeError(f"Expected 50 EEG and 50 annotation files; got {len(full_items)}")
    manifest = {"article_id": article["id"], "doi": article.get("doi"),
                "source": ARTICLE, "files": [{key: item[key] for key in
                                             ("name", "size", "computed_md5", "download_url")}
                                            for item in sorted(full_items, key=lambda x: x["name"])]}
    (args.root / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    items = full_items
    if args.ids:
        wanted = {f"{int(value):02d}" for value in args.ids}
        items = [item for item in items if item["name"].split("_")[2] in wanted]
        if len(items) != len(wanted) * 2:
            raise RuntimeError("Some requested participant IDs were not found")
    remaining = sum(item["size"] for item in items if not (args.root / item["name"]).exists())
    if shutil.disk_usage(args.root).free < remaining + 5 * 1024**3:
        raise RuntimeError("Less than 5 GiB spare space would remain after downloading")
    failures = []
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(fetch, item, args.root): item["name"] for item in items}
        for future in as_completed(futures):
            try:
                name, status = future.result()
                print(f"{status}: {name}", flush=True)
            except Exception as exc:
                failures.append((futures[future], str(exc)))
                print(f"FAILED: {futures[future]}: {exc}", flush=True)
    if failures:
        raise RuntimeError(f"{len(failures)} files failed; rerun to retry: {failures[:3]}")
    print(f"MPD_DF_DOWNLOAD_OK files={len(items)}", flush=True)


if __name__ == "__main__":
    main()

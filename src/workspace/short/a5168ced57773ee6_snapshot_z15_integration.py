"""Save a hash-checked, recoverable local copy of the current Z15 runtime."""
import hashlib
import json
from pathlib import Path

from run_soak_stage import ROOT, PROD, connect

OUT = ROOT / "eeg_apps_z15/output/integration_acceptance_20260927"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    metadata = json.loads((OUT / "board_snapshot.json").read_text(encoding="utf-8"))
    target = OUT / "snapshot"
    if target.exists():
        raise RuntimeError("Snapshot already exists; preserve it")
    target.mkdir()
    client = connect()
    try:
        entries = {}
        with client.open_sftp() as sftp:
            for name, expected in metadata["files_sha256"].items():
                path = target / name
                sftp.get(PROD + "/" + name, str(path))
                actual = sha(path)
                if actual != expected:
                    raise RuntimeError(f"Hash changed while copying {name}")
                entries[name] = {"sha256": actual, "bytes": path.stat().st_size}
            for unit, status in metadata["services"].items():
                destination = target / unit
                sftp.get(status["FragmentPath"], str(destination))
                entries[unit] = {"sha256": sha(destination),
                                 "bytes": destination.stat().st_size,
                                 "original_path": status["FragmentPath"]}
        snapshot = {"source": PROD, "files": entries,
                    "note": "Local recovery copy only; production board unchanged. "
                            "AP credentials and private recordings are intentionally excluded."}
        (OUT / "snapshot_manifest.json").write_text(
            json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"copied_files": len(entries),
                          "total_bytes": sum(row["bytes"] for row in entries.values()),
                          "all_hashes_match": True,
                          "manifest": str(OUT / "snapshot_manifest.json")}, ensure_ascii=False))
    finally:
        client.close()


if __name__ == "__main__":
    main()

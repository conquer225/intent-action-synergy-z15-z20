"""Restore content-pinned original paths/case into a new local workspace."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import sys


def relative_path(value):
    if not isinstance(value, str) or not value or "\\" in value or ":" in value:
        raise ValueError("expected a relative POSIX path")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in ("", ".", "..") for part in value.split("/")):
        raise ValueError("path escapes its root")
    return Path(*path.parts)


def digest(path):
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def restore(package, output):
    package, output = package.resolve(), output.resolve()
    if os.name == "nt":
        package = Path("\\\\?\\" + str(package).removeprefix("\\\\?\\"))
        output = Path("\\\\?\\" + str(output).removeprefix("\\\\?\\"))
    if output.exists():
        raise ValueError("output already exists; choose a new workspace")
    try:
        output.relative_to(package)
    except ValueError:
        pass
    else:
        raise ValueError("output must be outside the submission package")
    manifest = json.loads((package / "report/source_manifest.json").read_text(encoding="utf-8"))
    if manifest.get("schema_version") != 1 or not manifest.get("entries"):
        raise ValueError("unsupported or empty source manifest")
    prepared, targets = [], set()
    # Check the full source set before creating the output directory.
    for entry in manifest["entries"]:
        source = (package / relative_path(entry["package_path"])).resolve()
        source.relative_to(package)
        name = relative_path(entry["runtime_path"])
        key = name.as_posix().casefold()
        if key in targets:
            raise ValueError("duplicate runtime path: " + name.as_posix())
        targets.add(key)
        if not re.fullmatch("[0-9a-f]{64}", entry.get("sha256", "")):
            raise ValueError("invalid sha256 in manifest")
        if digest(source) != entry["sha256"]:
            raise ValueError("sha256 mismatch: " + entry["package_path"])
        if source.stat().st_size != entry["bytes"]:
            raise ValueError("size mismatch: " + entry["package_path"])
        prepared.append((source, name, entry["sha256"]))
    output.mkdir(parents=True, exist_ok=False)
    for source, name, expected in prepared:
        target = output / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        if digest(target) != expected:
            raise ValueError("post-copy sha256 mismatch: " + name.as_posix())
    return {"passed": True, "scope": "local_workspace_restore", "board_executed": False,
            "restored_files": len(prepared), "output": str(output)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        result, code = restore(args.package, args.output), 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        result, code = {"passed": False, "board_executed": False, "error": str(exc)}, 1
    print(json.dumps(result, ensure_ascii=True, indent=2))
    return code


if __name__ == "__main__":
    sys.exit(main())

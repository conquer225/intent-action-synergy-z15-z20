"""Check submission paths, the complete file list, and pinned source bytes offline."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import sys

REQUIRED_DIRS = ("src", "sim", "build", "board", "data", "skill", "report")
ARCHIVE_ROOT = "intent_action_synergy"
MAX_ARCHIVE_MEMBER_CHARACTERS = 120


def relative_path(value):
    if not value or "\\" in value or ":" in value:
        raise ValueError("expected a relative POSIX path")
    path = PurePosixPath(value)
    if path.is_absolute() or any(p in ("", ".", "..") for p in value.split("/")):
        raise ValueError("path escapes the package")
    return Path(*path.parts)


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def verify(package):
    package = package.resolve()
    if os.name == "nt":
        package = Path("\\\\?\\" + str(package).removeprefix("\\\\?\\"))
    for directory in REQUIRED_DIRS:
        if not (package / directory).is_dir():
            raise ValueError("missing required directory: " + directory)
    if not (package / "README.md").is_file():
        raise ValueError("missing root README.md")
    files = {}
    longest_member = 0
    for path in package.rglob("*"):
        name = path.relative_to(package).as_posix()
        if name == ".git" or name.startswith(".git/"):
            continue
        member_length = len(ARCHIVE_ROOT) + 1 + len(name)
        if member_length > MAX_ARCHIVE_MEMBER_CHARACTERS:
            raise ValueError("Windows ZIP member exceeds 120 characters: " + name)
        longest_member = max(longest_member, member_length)
        if path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction()):
            raise ValueError("link is not a portable package member: " + name)
        if name not in (".gitignore", ".gitattributes") and path.name not in ("README.md", "SKILL.md") and not re.fullmatch(r"[a-z0-9_][a-z0-9_.-]*", path.name):
            raise ValueError("invalid submission name: " + name)
        if path.is_file() and name != "sha256sums.txt":
            files[name] = path
    expected = {}
    for line in (package / "sha256sums.txt").read_text(encoding="ascii").splitlines():
        match = re.fullmatch(r"([0-9a-f]{64})  (.+)", line)
        if not match:
            raise ValueError("malformed sha256sums.txt entry")
        wanted, name = match.groups()
        relative_path(name)
        if name in expected:
            raise ValueError("duplicate checksum entry: " + name)
        expected[name] = wanted
    if set(files) != set(expected):
        missing = sorted(set(expected) - set(files))
        extra = sorted(set(files) - set(expected))
        raise ValueError("file list differs; missing=" + repr(missing[:5]) + "; unlisted=" + repr(extra[:5]))
    actual = {}
    total_bytes = 0
    for name, path in files.items():
        actual[name] = digest(path)
        total_bytes += path.stat().st_size
        if actual[name] != expected[name]:
            raise ValueError("sha256 mismatch: " + name)
    manifest = json.loads((package / "report/source_manifest.json").read_text(encoding="utf-8"))
    if manifest.get("schema_version") != 1 or not manifest.get("entries"):
        raise ValueError("unsupported or empty source manifest")
    runtime_paths = set()
    for entry in manifest["entries"]:
        name = relative_path(entry["package_path"]).as_posix()
        runtime = relative_path(entry["runtime_path"]).as_posix().casefold()
        if runtime in runtime_paths:
            raise ValueError("duplicate runtime path: " + runtime)
        runtime_paths.add(runtime)
        if name not in files or actual[name] != entry["sha256"] or files[name].stat().st_size != entry["bytes"]:
            raise ValueError("source manifest mismatch: " + name)
    return {"passed": True, "scope": "submission_integrity_only", "board_executed": False,
            "verified_files": len(files), "verified_bytes": total_bytes,
            "verified_source_files": len(runtime_paths),
            "max_archive_member_characters": longest_member,
            "naming_exceptions": ["README.md", "SKILL.md", ".gitignore", ".gitattributes"],
            "ignored_vcs_metadata": [".git/"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    try:
        result, code = verify(args.package), 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        result, code = {"passed": False, "board_executed": False, "error": str(exc)}, 1
    print(json.dumps(result, ensure_ascii=True, indent=2))
    return code


if __name__ == "__main__":
    sys.exit(main())

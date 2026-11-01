"""Create a checked source/bitstream bundle and a fresh relocatable Vivado project."""
import argparse
import hashlib
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

from eye_manifest import ROOT, verify


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vivado", default="D:/vivado/Vivado/2023.1/bin/vivado.bat")
    parser.add_argument("--output", type=Path, default=ROOT.parent / "Z15_Eye_Control_v1.zip")
    args = parser.parse_args()
    verify()
    tests = ("core", "uart", "sccb", "capture", "serial", "frame_store", "snapshot", "pipeline")
    for name in tests:
        log = ROOT / f"report/eye/tb_{name}.log"
        if not log.is_file() or f"PASS tb_{name}" not in log.read_text(errors="replace"):
            raise SystemExit(f"Missing passing evidence: {log}")
    staging = Path(tempfile.mkdtemp(prefix="eye_release_", dir=ROOT / "local")) / "z15_multimodal"
    staging.mkdir()
    roots = ("src", "sim", "build", "board", "tools", "docs", "report", "data", "skill",
             ".trellis", ".agents", ".claude", ".codex")
    candidates = [ROOT / p for p in ("README.md", "AGENTS.md", "THIRD_PARTY.md", ".gitignore", ".gitattributes")]
    for directory in roots:
        candidates.extend(p for p in (ROOT / directory).rglob("*") if p.is_file())
    copied = []
    for source in candidates:
        rel = source.relative_to(ROOT)
        if any(x in rel.parts for x in ("__pycache__", ".runtime", "node_modules", ".git")):
            continue
        if source.name in (".developer",) or source.suffix in (".pyc", ".dcp", ".wdb", ".jou", ".str"):
            continue
        if source.suffix == ".log" and not source.name.startswith("tb_"):
            continue
        dest = staging / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, dest)
        copied.append(rel)
    with (staging.parent / "create_project.log").open("w") as log:
        result = subprocess.run([args.vivado, "-mode", "batch", "-source", "build/eye/create_project.tcl"],
                                cwd=staging, stdout=log, stderr=subprocess.STDOUT,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), timeout=120)
    if result.returncode:
        raise SystemExit(f"Project generation failed: {staging.parent / 'create_project.log'}")
    xpr = Path("local/eye_vivado/z15_eye.xpr")
    xml = ET.parse(staging / xpr)
    inputs = xml.findall(".//File")
    if not inputs:
        raise SystemExit("Generated project contains no source files")
    for node in inputs:
        name = node.get("Path", "")
        if not name.startswith("$PPRDIR/"):
            raise SystemExit(f"Non-relocatable project input: {name}")
        target = ((staging / xpr).parent / name.removeprefix("$PPRDIR/")).resolve()
        if not target.is_relative_to(staging) or not target.is_file():
            raise SystemExit(f"Missing project input: {name}")
    copied.append(xpr)
    manifest = "".join(f"{hashlib.sha256((staging / rel).read_bytes()).hexdigest()}  {rel.as_posix()}\n"
                       for rel in sorted(copied))
    (staging / "MANIFEST.sha256").write_text(manifest, encoding="utf-8")
    copied.append(Path("MANIFEST.sha256"))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(args.output, "w", zipfile.ZIP_DEFLATED) as archive:
        for rel in sorted(copied):
            archive.write(staging / rel, (Path("z15_multimodal") / rel).as_posix())
    with zipfile.ZipFile(args.output) as archive:
        if archive.testzip() is not None:
            raise SystemExit("Archive CRC verification failed")
        for line in manifest.splitlines():
            expected, rel = line.split("  ", 1)
            if hashlib.sha256(archive.read("z15_multimodal/" + rel)).hexdigest() != expected:
                raise SystemExit(f"Archive hash mismatch: {rel}")
    checksum = hashlib.sha256(args.output.read_bytes()).hexdigest()
    args.output.with_suffix(".zip.sha256").write_text(checksum + "  " + args.output.name + "\n", encoding="ascii")
    print(f"PASS package: {len(copied)} files; {len(inputs)} project inputs; {args.output.stat().st_size} bytes")
    print(args.output)
    print("SHA256", checksum)


if __name__ == "__main__":
    main()

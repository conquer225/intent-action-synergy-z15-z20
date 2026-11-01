"""Reproducible offline evidence, including unchanged original Z15 source hashes."""
import compileall
from datetime import datetime, timezone, timedelta
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET
import zipfile

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from z20_compute.readiness import verify_baseline


def hls_artifacts():
    directory = HERE/"build/hls"
    report_path = directory/"result.json"
    result = json.loads(report_path.read_text()) if report_path.exists() else {}
    sources_match = bool(result.get("sources")) and all(
        (HERE/"hardware/hls"/name).is_file()
        and hashlib.sha256((HERE/"hardware/hls"/name).read_bytes()).hexdigest() == value
        for name, value in result.get("sources", {}).items())
    console = (directory/"console.txt").read_text(encoding="utf-8", errors="replace") if (directory/"console.txt").exists() else ""
    ip = directory/"mlp/solution/impl/ip"
    zip_valid = False
    try:
        ET.parse(ip/"component.xml")
        packages = list(ip.glob("*.zip"))
        if len(packages) == 1:
            with zipfile.ZipFile(packages[0]) as package:
                zip_valid = package.testzip() is None and "component.xml" in package.namelist()
    except (OSError, ValueError, ET.ParseError, zipfile.BadZipFile):
        pass
    cosim_path = directory/"cosim-result.json"
    cosim = json.loads(cosim_path.read_text()) if cosim_path.exists() else {}
    return dict(sources_match=sources_match, c_simulation="CSim done with 0 errors" in console,
                synthesis="Finished Creating RTL model" in console, ip_xml_and_zip_valid=zip_valid,
                build_exit_code=result.get("exit_code"), packaging_exit_code=result.get("packaging_exit_code"),
                rtl_numeric_passed=cosim.get("passed") is True and cosim.get("sources") == result.get("sources"),
                rtl_simulator_exit_code=cosim.get("simulator_exit"), board_executed=False)


def main():
    output = HERE/"report"
    output.mkdir(exist_ok=True)
    checks = {}
    for name, command, paths in [
        ("new_module", [sys.executable, "-m", "unittest", "discover", "-s", str(HERE/"tests"), "-v"], [HERE]),
        ("existing_continuous_video", [sys.executable, "-m", "unittest", "discover", "-s",
                  str(HERE.parent/"vision_demo/tests"), "-p", "test_continuous.py", "-v"], [HERE.parent/"vision_demo"]),
        ("existing_deferred_video", [sys.executable, "-m", "unittest", "discover", "-s",
                  str(HERE.parent/"vision_demo/tests"), "-p", "test_deferred_video.py", "-v"], [HERE.parent/"vision_demo"])]:
        environment = dict(os.environ, PYTHONPATH=os.pathsep.join(map(str, paths)))
        result = subprocess.run(command, cwd=HERE.parents[1], env=environment,
                                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
        text = result.stdout+result.stderr
        (output/(name+".txt")).write_text(text, encoding="utf-8")
        checks[name] = dict(passed=result.returncode == 0, exit_code=result.returncode,
                            summary=text[text.rfind("Ran "):].strip())
    checks["compile"] = dict(passed=compileall.compile_dir(HERE/"z20_compute", quiet=1))
    baseline = json.loads((output/"z15_baseline.json").read_text(encoding="utf-8"))
    from z20_compute.reviewed_baseline import verify_reviewed
    review=json.loads((output/'z15_reviewed_changes_20261027.json').read_text(encoding='utf-8'))
    checks['z15_baseline']=verify_reviewed(HERE.parents[1],baseline,review)
    checks["hls"] = hls_artifacts()
    digest = hashlib.sha256()
    source_count = 0
    for directory in ("z20_compute", "tests", "hardware"):
        for path in sorted((HERE/directory).rglob("*")):
            if path.is_file() and "__pycache__" not in path.parts:
                digest.update(path.relative_to(HERE).as_posix().encode())
                digest.update(path.read_bytes())
                source_count += 1
    report = dict(date=datetime.now(timezone(timedelta(hours=8))).isoformat(), python=sys.version,
                  tested_source_tree_sha256=digest.hexdigest(), tested_source_files=source_count,
                  software_passed=all(checks[name]["passed"] for name in checks if name != "hls"),
                  board_executed=False, checks=checks)
    (output/"offline_verification.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return int(not report["software_passed"])


if __name__ == "__main__": raise SystemExit(main())

"""Use the repository's verified Windows HLS environment; never edit the tools."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
from tool_environment import prepare

HERE = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("D:/vivado/Vitis_HLS/2023.1"))
    args = parser.parse_args()
    executable, environment = prepare(args.root)
    out = HERE/"build/hls"
    out.mkdir(parents=True, exist_ok=True)
    with (out/"console.txt").open("w", encoding="utf-8") as log:
        result = subprocess.run([str(executable), "-f",
                                 str(HERE/"hardware/hls/build.tcl")], cwd=HERE,
                                env=environment, stdout=log, stderr=subprocess.STDOUT)
    text = (out/"console.txt").read_text(encoding="utf-8", errors="replace")
    ip = out/"mlp/solution/impl/ip/component.xml"
    packaging = None
    script = ip.parent/"run_ippack.tcl"
    if not ip.exists() and script.exists() and "Finished Command csynth_design" in text:
        vivado = args.root.parents[1]/"Vivado"/args.root.name
        vivado_executable, vivado_environment = prepare(vivado)
        with (out/"packaging.txt").open("w", encoding="utf-8") as log:
            packaging = subprocess.run([str(vivado_executable), "-mode", "batch",
                                        "-nojournal", "-source", str(script.resolve())], cwd=ip.parent,
                                       env=vivado_environment, stdout=log, stderr=subprocess.STDOUT).returncode
    passed = ("PASS: shared D->32->3" in text and "Finished Command csynth_design" in text
              and ip.is_file() and (result.returncode == 0 or packaging == 0))
    report = dict(passed=passed, c_simulation_passed="CSim done with 0 errors" in text,
                  synthesis_passed="Finished Creating RTL model" in text, ip_generated=ip.is_file(),
                  process_exit_clean=result.returncode == 0 or packaging == 0,
                  exit_code=result.returncode, packaging_exit_code=packaging,
                  scope="HLS C simulation/synthesis/IP export only; no board implementation or test",
                  sources={p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                           for p in (HERE/"hardware/hls").glob("*") if p.is_file()})
    (out/"result.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(text[-2500:])
    print(json.dumps(report, indent=2))
    return int(not passed)


if __name__ == "__main__":
    raise SystemExit(main())

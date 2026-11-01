"""Package offline source, unchanged EEG baseline and generated HLS IP."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile
from z20_compute.reviewed_baseline import verify_reviewed

HERE = Path(__file__).resolve().parent


def create_bundle(output):
    output = Path(output)
    baseline = json.loads((HERE/"report/z15_baseline.json").read_text(encoding="utf-8"))
    review=json.loads((HERE/'report/z15_reviewed_changes_20261027.json').read_text(encoding='utf-8'))
    baseline_check=verify_reviewed(HERE.parents[1],baseline,review)
    if not baseline_check['passed']:
        raise ValueError('unreviewed Z15 baseline changes: '+str(baseline_check['unreviewed_changes']))
    files = {}
    for directory in ("z20_compute", "hardware", "examples"):
        for path in (HERE/directory).rglob("*"):
            if path.is_file() and "__pycache__" not in path.parts:
                files[path.relative_to(HERE).as_posix()] = path
    for name in ("README.md", "GLOSSARY.md", "HARDWARE.md", "STEREO_BOARD.md", "requirements.txt", "requirements-pc.txt",
                 "build_stereo_boot.py", "build_stereo_package.py", "build_stereo_sd.py", "verify_stereo_boot.py", "tool_environment.py"):
        path = HERE/name
        if not path.is_file():
            raise FileNotFoundError(path)
        files[name] = path
    for path in (HERE.parents[1]/"multimodal/vendor/runtime").iterdir():
        if path.is_file() and path.suffix in (".py", ".json", ".npz"):
            files["legacy/"+path.name] = path
    for path in (HERE/"report").glob("*"):
        if path.is_file():
            files["report/"+path.name] = path
    for path in (HERE/"build/hls/mlp/solution/impl/ip").glob("*.zip"):
        with zipfile.ZipFile(path) as package:
            if package.testzip() is not None:
                raise ValueError("generated HLS IP archive is damaged")
        files["hardware/ip/"+path.name] = path
    for name in ("result.json", "cosim-result.json"):
        path = HERE/"build/hls"/name
        if path.exists():
            files["report/hls-"+name] = path
    manifest = dict(kind="offline-source-and-hls-ip", board_executed=False,baseline_check=baseline_check,
                    includes_trained_upgrade_models=False, includes_board_bitstream=False,
                    note="legacy weights are the original Z15 comparison baseline; four new classifiers require labeled data",
                    files={name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in files.items()})
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as package:
        for name, path in sorted(files.items()):
            package.write(path, name)
        package.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=HERE/"artifacts/z20-offline.zip")
    args = parser.parse_args()
    path = create_bundle(args.output)
    print(json.dumps(dict(path=str(path), bytes=path.stat().st_size,
                         sha256=hashlib.sha256(path.read_bytes()).hexdigest())))

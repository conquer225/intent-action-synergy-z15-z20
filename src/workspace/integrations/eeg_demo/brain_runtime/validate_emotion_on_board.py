"""Stage the emotion runtime in /tmp and compare ARM results before deployment."""

import argparse
import hashlib
import json
from pathlib import Path
import shlex
import subprocess
import sys

import paramiko

from deploy_sqi_update import run

HERE = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifacts", type=Path, required=True)
    parser.add_argument("--host", default="192.168.2.99")
    parser.add_argument("--user", default="xilinx")
    parser.add_argument("--password", default="xilinx")
    args = parser.parse_args()
    artifact_dir = args.artifacts.resolve()
    files = [HERE / "cyton_sqi.py", HERE / "verify_emotion_runtime.py"] + [
        artifact_dir / name for name in ("model_6ch.json", "runtime_fixture.npz", "runtime_expected.json")]
    pc = subprocess.run([sys.executable, str(HERE / "verify_emotion_runtime.py"),
                         "--model", str(files[2]), "--fixture", str(files[3]),
                         "--expected", str(files[4])], check=True, capture_output=True, text=True)
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(args.host, username=args.user, password=args.password, timeout=10)
    try:
        stage = run(client, "mktemp -d /tmp/guardianloop-emotion-XXXXXX").strip()
        with client.open_sftp() as sftp:
            for path in files:
                sftp.put(str(path), stage + "/" + path.name)
        arm_output = run(client, "cd " + shlex.quote(stage) +
                         " && /usr/local/share/pynq-venv/bin/python3 verify_emotion_runtime.py"
                         " --model model_6ch.json --fixture runtime_fixture.npz"
                         " --expected runtime_expected.json", timeout=60)
        report = {"pc": json.loads(pc.stdout), "arm": json.loads(arm_output),
                  "board": args.host, "remote_stage": stage,
                  "model_sha256": hashlib.sha256(files[2].read_bytes()).hexdigest(),
                  "measurement_scope": "ARM feature extraction plus LDA; excludes acquisition, SQI, network and PL"}
        (artifact_dir / "board_validation.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report))
    finally:
        client.close()


if __name__ == "__main__":
    main()

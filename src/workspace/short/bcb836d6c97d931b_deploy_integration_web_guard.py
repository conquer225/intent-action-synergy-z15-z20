"""Board-test and deploy the narrow /api/status stale-result guard."""
import hashlib
import json
from pathlib import Path
import shlex
import time

import requests

from run_soak_stage import ROOT, PROD, connect, command

OUT = ROOT / "eeg_apps_z15/output/integration_acceptance_20260927"
PYTHON = "/usr/local/share/pynq-venv/bin/python3"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def sudo(client, args):
    stdin, stdout, stderr = client.exec_command("sudo -S -p '' " + args, timeout=45)
    stdin.write("xilinx\n")
    stdin.flush()
    message = stdout.read().decode(errors="replace") + stderr.read().decode(errors="replace")
    if stdout.channel.recv_exit_status():
        raise RuntimeError("sudo operation failed: " + message[-1000:])


def main():
    marker = OUT / "web_guard_deployment.json"
    if marker.exists():
        raise RuntimeError("Existing deployment record; do not overwrite")
    before = json.loads((OUT / "board_snapshot.json").read_text(encoding="utf-8"))
    expected = before["files_sha256"]["guardianloop_web.py"]
    candidate = ROOT / "pynq_guardianloop/guardianloop_web.py"
    candidate_hash = sha(candidate)
    stage = "/home/xilinx/jupyter_notebooks/integration_web_guard_" + time.strftime("%Y%m%d-%H%M%S")
    backup = PROD + "/backup-integration-web-" + time.strftime("%Y%m%d-%H%M%S")
    client = connect()
    installed = False
    try:
        with client.open_sftp() as sftp:
            sftp.get(PROD + "/guardianloop_web.py", str(OUT / "web_before_deploy.py"))
            if sha(OUT / "web_before_deploy.py") != expected:
                raise RuntimeError("Board web file changed after audit")
            sftp.mkdir(stage)
            sftp.put(str(candidate), stage + "/guardianloop_web.py")
            sftp.put(str(ROOT / "pynq_guardianloop/test_seed_shadow_web.py"),
                     stage + "/test_seed_shadow_web.py")
        test_command = ("env PYTHONPATH=" + shlex.quote(stage + ":" + PROD)
                        + " OPENBLAS_NUM_THREADS=1 " + PYTHON
                        + " -m unittest test_seed_shadow_web")
        tests = command(client, test_command)
        if "OK" not in tests:
            raise RuntimeError("Board regression test did not report OK")
        (OUT / "board_web_guard_tests.txt").write_text(tests, encoding="utf-8")
        with client.open_sftp() as sftp:
            sftp.mkdir(backup)
            sftp.put(str(OUT / "web_before_deploy.py"), backup + "/guardianloop_web.py")
            sftp.put(str(candidate), PROD + "/guardianloop_web.py.integration-new")
            sftp.get(PROD + "/guardianloop_web.py.integration-new", str(OUT / "web_uploaded.py"))
            if sha(OUT / "web_uploaded.py") != candidate_hash:
                raise RuntimeError("Uploaded web file hash mismatch")
            sftp.posix_rename(PROD + "/guardianloop_web.py.integration-new",
                             PROD + "/guardianloop_web.py")
            installed = True
        sudo(client, "systemctl restart guardianloop-web.service")
        time.sleep(4)
        service = command(client, "systemctl show guardianloop-web -p MainPID -p NRestarts -p ActiveState")
        if "ActiveState=active" not in service:
            raise RuntimeError("Web service not active: " + service)
        actual = command(client, "sha256sum " + PROD + "/guardianloop_web.py").split()[0]
        if actual != candidate_hash:
            raise RuntimeError("Installed web hash mismatch")
        health = requests.get("http://192.168.2.99:9102/healthz", timeout=6)
        if health.status_code != 200:
            raise RuntimeError("Web health check failed")
        record = {"baseline_sha256": expected, "deployed_sha256": candidate_hash,
                  "backup": backup + "/guardianloop_web.py", "service": service,
                  "health_http": health.status_code,
                  "scope": "web service only; acquisition/AP/PL/model unchanged"}
        marker.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(record, ensure_ascii=False, indent=2))
    except Exception:
        if installed:
            with client.open_sftp() as sftp:
                sftp.put(str(OUT / "web_before_deploy.py"), PROD + "/guardianloop_web.py.rollback")
                sftp.posix_rename(PROD + "/guardianloop_web.py.rollback",
                                 PROD + "/guardianloop_web.py")
            sudo(client, "systemctl restart guardianloop-web.service")
        raise
    finally:
        client.close()


if __name__ == "__main__":
    main()

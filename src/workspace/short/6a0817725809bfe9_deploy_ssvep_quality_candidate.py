"""Guarded, reversible rollout of the already-audited ARM SSVEP modules.

Only three Python files are replaced. The formal service is stopped for the
short rename window; neither PL nor boot media is touched. Re-run with
``rollback`` to restore the saved originals if post-install replay fails.
"""

import argparse
import hashlib
import json
import shlex
import time
from pathlib import Path

from run_accepted_bench_load import PROD, ROOT, connect, remote
from run_ssvep_quality_gate import CANDIDATE, OUT


MODULES = ("ssvep_core.py", "ssvep_stream.py", "ssvep_shadow.py")
BITSTREAMS = {
    "guardianloop_pynq.bit": "c39b891704471a712fb7be3591841af1dd6791387957b873b11450c99eca41ca",
    "guardianloop_pynq.hwh": "2ab7ffa36398be4eee20d90512c7f1c6d29a7066c9d1bf0683a3bcad2501f92b",
}
LEDGER = OUT / "deployment.json"


def digest_remote(sftp, path):
    with sftp.open(path, "rb") as stream:
        return hashlib.sha256(stream.read()).hexdigest()


def sudo(client, command):
    stdin, stdout, stderr = client.exec_command("sudo -S -p '' " + command, timeout=40)
    stdin.write("xilinx\n")
    stdin.flush()
    output = stdout.read().decode(errors="replace") + stderr.read().decode(errors="replace")
    if stdout.channel.recv_exit_status():
        raise RuntimeError(output[-3000:])
    return output


def save(ledger):
    LEDGER.write_text(json.dumps(ledger, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def check_files(sftp, expected):
    return {
        name: digest_remote(sftp, PROD + "/" + name)
        for name in expected
    }


def check_web(client):
    payload = json.loads(remote(client, "curl --max-time 5 -fsS http://127.0.0.1:9102/api/ssvep-shadow"))
    if payload["live"]["source"] != "live" or payload["live"]["control_enabled"] is not False:
        raise RuntimeError("SSVEP live endpoint source/control safety changed")
    replay = payload.get("replay", {})
    if replay and replay.get("source") != "replay":
        raise RuntimeError("SSVEP replay endpoint was not separated")
    return {"live_state": payload["live"]["state"],
            "live_source": payload["live"]["source"],
            "control_enabled": payload["live"]["control_enabled"],
            "replay_source": replay.get("source")}


def restore(client, ledger):
    backup = ledger["backup"]
    sudo(client, "systemctl stop guardianloop-cyton.service")
    with client.open_sftp() as sftp:
        for name in MODULES:
            if digest_remote(sftp, backup + "/" + name) != ledger["production_before"][name]:
                raise RuntimeError("Backup corrupted: " + name)
        for name in MODULES:
            remote(client, "cp -p " + shlex.quote(backup + "/" + name) + " "
                          + shlex.quote(PROD + "/" + name + ".rollback-new"))
            sftp.posix_rename(PROD + "/" + name + ".rollback-new", PROD + "/" + name)
        current = check_files(sftp, ledger["production_before"])
    if current != ledger["production_before"]:
        raise RuntimeError("Restored module hashes do not match backup ledger")
    sudo(client, "systemctl start guardianloop-cyton.service")
    ledger["phase"] = "rolled_back"
    ledger["production_after_rollback"] = current
    save(ledger)
    return ledger


def install():
    if LEDGER.exists():
        raise RuntimeError("Existing deployment ledger; inspect or roll back before retrying")
    audit = json.loads((OUT / "audit.json").read_text(encoding="utf-8"))
    if not audit["candidate_isolated_gate_pass"] or not audit["event_parity"]["passed"]:
        raise RuntimeError("Isolation gate did not pass")
    expected_old = {name: audit["production_sha256"][name] for name in MODULES}
    expected_new = {name: audit["candidate_sha256"][name] for name in MODULES}
    for name in MODULES:
        if hashlib.sha256(CANDIDATE[name].read_bytes()).hexdigest() != expected_new[name]:
            raise RuntimeError("Local candidate changed: " + name)
    client = connect()
    installed = False
    service_stopped = False
    ledger = None
    try:
        with client.open_sftp() as sftp:
            if check_files(sftp, expected_old) != expected_old:
                raise RuntimeError("Board production modules changed after paired audit")
            if check_files(sftp, BITSTREAMS) != BITSTREAMS:
                raise RuntimeError("Formal PL bitstream/HWH changed; aborting ARM deployment")
        web_before = check_web(client)
        backup = PROD + "/backup-ssvep-arm-" + time.strftime("%Y%m%d-%H%M%S")
        staging = backup + "/candidate"
        with client.open_sftp() as sftp:
            sftp.mkdir(backup)
            sftp.mkdir(staging)
        ledger = {"phase": "preflight", "backup": backup,
                  "staging": staging,
                  "production_before": expected_old, "candidate": expected_new,
                  "bitstream_hashes": BITSTREAMS, "web_before": web_before,
                  "rollback": "python deploy_ssvep_quality_candidate.py rollback"}
        save(ledger)
        for name in MODULES:
            remote(client, "cp -p " + shlex.quote(PROD + "/" + name) + " "
                          + shlex.quote(backup + "/" + name))
        with client.open_sftp() as sftp:
            backed_up = {name: digest_remote(sftp, backup + "/" + name) for name in MODULES}
            if backed_up != expected_old:
                raise RuntimeError("Backup verification failed")
            for name in MODULES:
                staged_path = staging + "/" + name
                sftp.put(str(CANDIDATE[name]), staged_path)
                sftp.chmod(staged_path, 0o664)
                if digest_remote(sftp, staged_path) != expected_new[name]:
                    raise RuntimeError("Upload verification failed: " + name)
        remote(client, "cd " + shlex.quote(staging) + " && env PYTHONPATH="
                      + shlex.quote(staging + ":" + PROD) + " XILINX_XRT=/usr "
                      + "/usr/local/share/pynq-venv/bin/python3 -c "
                      + shlex.quote("import ssvep_shadow, ssvep_stream, ssvep_core"))
        ledger["phase"] = "staged"
        save(ledger)
        sudo(client, "systemctl stop guardianloop-cyton.service")
        service_stopped = True
        with client.open_sftp() as sftp:
            for name in MODULES:
                sftp.posix_rename(staging + "/" + name, PROD + "/" + name)
                installed = True
            after = check_files(sftp, expected_new)
            bit_after = check_files(sftp, BITSTREAMS)
        if after != expected_new or bit_after != BITSTREAMS:
            raise RuntimeError("Post-rename module or PL hash mismatch")
        remote(client, "cd " + shlex.quote(PROD) + " && env PYTHONPATH=" + shlex.quote(PROD)
                      + " XILINX_XRT=/usr /usr/local/share/pynq-venv/bin/python3 -c "
                      + shlex.quote("import cyton_guardianloop, ssvep_shadow, ssvep_stream, ssvep_core"))
        sudo(client, "systemctl start guardianloop-cyton.service")
        service_stopped = False
        time.sleep(3)
        ledger["production_after"] = after
        ledger["bitstream_after"] = bit_after
        ledger["web_after"] = check_web(client)
        ledger["services_after"] = remote(
            client, "systemctl show guardianloop-cyton guardianloop-web "
                    "-p MainPID -p NRestarts -p ActiveState -p SubState"
        )
        ledger["phase"] = "installed_pending_replay"
        save(ledger)
        print(json.dumps(ledger, indent=2, ensure_ascii=False), flush=True)
    except Exception:
        if installed and ledger is not None:
            restore(client, ledger)
        elif service_stopped:
            sudo(client, "systemctl start guardianloop-cyton.service")
        raise
    finally:
        client.close()


def rollback():
    ledger = json.loads(LEDGER.read_text(encoding="utf-8"))
    if ledger["phase"] == "rolled_back":
        print("Already rolled back")
        return
    client = connect()
    try:
        with client.open_sftp() as sftp:
            current = check_files(sftp, ledger["candidate"])
        if current != ledger["candidate"]:
            raise RuntimeError("Installed files differ from this ledger; do not overwrite another change")
        print(json.dumps(restore(client, ledger), indent=2, ensure_ascii=False), flush=True)
    finally:
        client.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("install", "rollback"))
    args = parser.parse_args()
    {"install": install, "rollback": rollback}[args.action]()


if __name__ == "__main__":
    main()

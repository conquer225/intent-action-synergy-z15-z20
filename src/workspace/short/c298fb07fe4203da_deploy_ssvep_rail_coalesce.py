"""Deploy only the audited SSVEP shadow module, with exact-hash rollback."""
import hashlib
import json
from pathlib import Path
import time

from run_soak_stage import ROOT, PROD, connect, command

OUT = ROOT / "eeg_apps_z15/output/ssvep_rail_coalesce_20260927"
BASELINE = "2a152be9f1791bb02b8d124a207dacd30ecef744d01b65e3a71a8a95a378157c"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def sudo(client, args):
    stdin, stdout, stderr = client.exec_command("sudo -S -p '' " + args, timeout=40)
    stdin.write("xilinx\n")
    stdin.flush()
    output = stdout.read().decode(errors="replace") + stderr.read().decode(errors="replace")
    if stdout.channel.recv_exit_status():
        raise RuntimeError(output[-2000:])
    return output


def main():
    marker = OUT / "deployment.json"
    if marker.exists():
        raise RuntimeError("Already deployed; inspect deployment.json")
    candidate = OUT / "ssvep_shadow.py"
    candidate_hash = sha(candidate)
    client = connect()
    backup = PROD + "/backup-ssvep-rail-" + time.strftime("%Y%m%d-%H%M%S")
    installed = False
    try:
        with client.open_sftp() as sftp:
            current = OUT / "deployment-current.py"
            sftp.get(PROD + "/ssvep_shadow.py", str(current))
            if sha(current) != BASELINE:
                raise RuntimeError("Production SSVEP hash changed; refusing overwrite")
            sftp.mkdir(backup)
            sftp.put(str(current), backup + "/ssvep_shadow.py")
            sftp.put(str(candidate), PROD + "/ssvep_shadow.py.rail-new")
            sftp.get(PROD + "/ssvep_shadow.py.rail-new", str(OUT / "uploaded.py"))
            if sha(OUT / "uploaded.py") != candidate_hash:
                raise RuntimeError("Upload hash mismatch")
            sftp.posix_rename(PROD + "/ssvep_shadow.py.rail-new", PROD + "/ssvep_shadow.py")
            installed = True
        sudo(client, "systemctl restart guardianloop-cyton.service")
        time.sleep(8)
        service = command(client, "systemctl show guardianloop-cyton -p MainPID -p NRestarts -p ActiveState")
        if "ActiveState=active" not in service:
            raise RuntimeError("Service not active after restart: " + service)
        board_hash = command(client, "sha256sum " + PROD + "/ssvep_shadow.py").split()[0]
        if board_hash != candidate_hash:
            raise RuntimeError("Installed hash mismatch")
        marker.write_text(json.dumps({"backup": backup, "baseline": BASELINE,
                                      "candidate": candidate_hash, "service": service}, indent=2),
                          encoding="utf-8")
        print(marker.read_text(), flush=True)
    except Exception:
        if installed:
            with client.open_sftp() as sftp:
                sftp.put(str(OUT / "deployment-current.py"), PROD + "/ssvep_shadow.py.rollback")
                sftp.posix_rename(PROD + "/ssvep_shadow.py.rollback", PROD + "/ssvep_shadow.py")
            sudo(client, "systemctl restart guardianloop-cyton.service")
        raise
    finally:
        client.close()


if __name__ == "__main__":
    main()

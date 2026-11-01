"""Safely deploy the current ARM-only-default Cyton program on the Z15.

This does not install a kernel driver, load a PL overlay, or change boot files.
It refuses to replace unexpected production revisions and retains an exact
on-board backup of every file it replaces.
"""

import hashlib
import shlex
import time
from pathlib import Path

from run_soak_stage import PROD, ROOT, command, connect


PYTHON = "/usr/local/share/pynq-venv/bin/python3"
EXPECTED = {
    "cyton_guardianloop.py": "2124538c796b7b23bd49f74b9710ef3942efb960bf185a83e5574211985592d1",
    "cyton_sqi.py": "3f311e8a7caa858e3a0c640ed11ccee59334664e6e3d83bf38dc662e034e758e",
}
SOURCES = ("cyton_guardianloop.py", "cyton_sqi.py", "pl_causal_filter.py")
TESTS = ("test_cyton_sqi.py", "test_pl_causal_filter.py")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def remote_digest(client, path):
    return command(client, "sha256sum " + shlex.quote(path)).split()[0]


def sudo(client, argv):
    stdin, stdout, stderr = client.exec_command("sudo -S -p '' " + argv, timeout=30)
    stdin.write("xilinx\n")
    stdin.flush()
    output = stdout.read().decode(errors="replace") + stderr.read().decode(errors="replace")
    if stdout.channel.recv_exit_status():
        raise RuntimeError(output[-2000:])
    return output


def main():
    source = ROOT / "pynq_guardianloop"
    stamp = time.strftime("%Y%m%d-%H%M%S")
    stage = f"/home/xilinx/guardianloop_arm_restore_{stamp}"
    backup = f"{PROD}/backup-arm-restore-{stamp}"
    hashes = {name: digest(source / name) for name in SOURCES}
    client = connect()
    stopped = False
    installed = []
    try:
        if command(client, "uname -r").strip() != "5.4.0-xilinx-v2020.2":
            raise RuntimeError("Unexpected Z15 kernel; no installation attempted")
        for name, expected in EXPECTED.items():
            actual = remote_digest(client, f"{PROD}/{name}")
            if actual != expected:
                raise RuntimeError(f"Production {name} changed since audit: {actual}")
        with client.open_sftp() as sftp:
            try:
                sftp.stat(f"{PROD}/pl_causal_filter.py")
            except FileNotFoundError:
                pass
            else:
                raise RuntimeError("Unexpected production PL wrapper; inspect before replacing")
            sftp.mkdir(stage)
            for name in SOURCES + TESTS:
                sftp.put(str(source / name), f"{stage}/{name}")
        for name in SOURCES:
            if remote_digest(client, f"{stage}/{name}") != hashes[name]:
                raise RuntimeError(f"Staged {name} failed SHA-256 check")
        environment = f"cd {shlex.quote(stage)} && PYTHONPATH={shlex.quote(PROD)} XILINX_XRT=/usr "
        command(client, environment + f"{PYTHON} -m py_compile " + " ".join(SOURCES))
        print(command(client, environment + f"{PYTHON} -m unittest test_cyton_sqi test_pl_causal_filter 2>&1"))
        print(command(client, environment + f"{PYTHON} -c 'import cyton_guardianloop; print(\"ARM_IMPORT_OK\")'"))

        # Recheck immediately before the production service is stopped.
        for name, expected in EXPECTED.items():
            if remote_digest(client, f"{PROD}/{name}") != expected:
                raise RuntimeError(f"Production {name} changed during staging")
        with client.open_sftp() as sftp:
            sftp.mkdir(backup)
        for name in EXPECTED:
            command(client, f"cp -a {shlex.quote(PROD + '/' + name)} {shlex.quote(backup + '/' + name)}")
            if remote_digest(client, f"{backup}/{name}") != EXPECTED[name]:
                raise RuntimeError(f"Backup of {name} failed SHA-256 check")
        sudo(client, "systemctl stop guardianloop-cyton.service")
        stopped = True
        with client.open_sftp() as sftp:
            for name in SOURCES:
                temporary = f"{PROD}/{name}.arm-new-{stamp}"
                sftp.put(str(source / name), temporary)
                if remote_digest(client, temporary) != hashes[name]:
                    raise RuntimeError(f"Uploaded {name} failed SHA-256 check")
                sftp.posix_rename(temporary, f"{PROD}/{name}")
                installed.append(name)
        command(client, f"cd {shlex.quote(PROD)} && PYTHONDONTWRITEBYTECODE=1 {PYTHON} -B "
                "-c 'import cyton_guardianloop; print(\"PRODUCTION_ARM_IMPORT_OK\")'")
        sudo(client, "systemctl start guardianloop-cyton.service")
        stopped = False
        time.sleep(2)
        service = command(client, "systemctl show guardianloop-cyton.service -p ActiveState -p MainPID -p ExecStart")
        if "ActiveState=active" not in service:
            raise RuntimeError("Cyton service did not start: " + service)
        for name in SOURCES:
            if remote_digest(client, f"{PROD}/{name}") != hashes[name]:
                raise RuntimeError(f"Installed {name} failed final SHA-256 check")
        print(f"ARM_RESTORE_OK backup={backup}")
        print(service)
        print(command(client, "curl -fsS --max-time 5 http://127.0.0.1:9102/healthz"))
    except BaseException:
        if installed:
            try:
                sudo(client, "systemctl stop guardianloop-cyton.service")
                with client.open_sftp() as sftp:
                    for name in installed:
                        if name in EXPECTED:
                            command(client, f"cp -a {shlex.quote(backup + '/' + name)} {shlex.quote(PROD + '/' + name)}")
                        else:
                            sftp.remove(f"{PROD}/{name}")
                sudo(client, "systemctl start guardianloop-cyton.service")
                stopped = False
                print("ARM_RESTORE_ROLLED_BACK")
            except BaseException as rollback_error:
                print(f"ARM_ROLLBACK_NEEDS_MANUAL_CHECK: {rollback_error}")
        elif stopped:
            sudo(client, "systemctl start guardianloop-cyton.service")
        raise
    finally:
        client.close()


if __name__ == "__main__":
    main()

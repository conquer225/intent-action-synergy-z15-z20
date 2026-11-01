"""Deploy the ARM SQI/emotion update without replacing the PL overlay."""

import argparse
import shlex
import time
from pathlib import Path

import paramiko


HERE = Path(__file__).resolve().parent
REMOTE_DIR = "/home/xilinx/jupyter_notebooks/guardianloop_pynq"
FILES = ("cyton_sqi.py", "cyton_covariance.py", "gameemo_covariance_svm.npz",
         "cyton_trial_recorder.py", "gameemo_emotion_model.json", "cyton_guardianloop.py",
         "cyton_fatigue.py", "cyton_fatigue_overlap4.json",
         "guardianloop_web.py", "guardianloop-cyton.service")
FATIGUE_MODEL = HERE.parent / "viformer_z15" / "output" / "cyton_montage_fatigue_v2" / "cyton_fatigue_overlap4.json"


def run(client, command, timeout=30):
    _, stdout, stderr = client.exec_command(command, timeout=timeout)
    output = stdout.read().decode("utf-8", errors="replace")
    errors = stderr.read().decode("utf-8", errors="replace")
    status = stdout.channel.recv_exit_status()
    if status:
        raise RuntimeError(f"command failed ({status}): {errors or output}")
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="192.168.2.99")
    parser.add_argument("--user", default="xilinx")
    parser.add_argument("--password", default="xilinx")
    parser.add_argument("--emotion-model", type=Path, default=HERE / "gameemo_emotion_model.json")
    parser.add_argument("--enable-cyton", action="store_true",
                        help="enable the direct Cyton service at boot for standalone operation")
    args = parser.parse_args()
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(args.host, username=args.user, password=args.password, timeout=10)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    try:
        run(client, f"mkdir -p {REMOTE_DIR}")
        with client.open_sftp() as sftp:
            for name in FILES:
                source = (args.emotion_model if name == "gameemo_emotion_model.json" else
                          FATIGUE_MODEL if name == "cyton_fatigue_overlap4.json" else HERE / name)
                target = f"{REMOTE_DIR}/{name}"
                backup = f"{target}.before-sqi-{stamp}"
                run(client, f"test ! -f {shlex.quote(target)} || cp -a {shlex.quote(target)} {shlex.quote(backup)}")
                staged = target + ".new"
                sftp.put(str(source), staged)
                try:
                    sftp.posix_rename(staged, target)
                except OSError:
                    try:
                        sftp.remove(target)
                    except FileNotFoundError:
                        pass
                    sftp.rename(staged, target)
                print(f"deployed={target} backup={backup}")
        password = shlex.quote(args.password)
        service_file = "/etc/systemd/system/guardianloop-cyton.service"
        run(client, f"printf '%s\\n' {password} | sudo -S cp -a "
            f"{shlex.quote(service_file)} {shlex.quote(service_file + '.before-sqi-' + stamp)}")
        command = (
            f"printf '%s\\n' {password} | sudo -S sh -c " + shlex.quote(
                "set -e; install -m 0644 " + REMOTE_DIR + "/guardianloop-cyton.service "
                + service_file + "; systemctl daemon-reload; "
                "systemctl restart guardianloop-web.service; "
                + ("systemctl enable guardianloop-cyton.service; " if args.enable_cyton else "")
                + "if systemctl is-active --quiet guardianloop-cyton.service; then "
                "systemctl restart guardianloop-cyton.service; fi"
            )
        )
        run(client, command)
        time.sleep(3)
        print(run(client,
            "echo WEB=$(systemctl is-active guardianloop-web.service); "
            "echo CYTON=$(systemctl is-active guardianloop-cyton.service || true); "
            "python3 -m py_compile " + " ".join(f"{REMOTE_DIR}/{name}" for name in
                ("cyton_sqi.py", "cyton_covariance.py", "cyton_fatigue.py", "cyton_trial_recorder.py",
                 "cyton_guardianloop.py", "guardianloop_web.py")) + "; "
            f"cd {REMOTE_DIR}; /usr/local/share/pynq-venv/bin/python3 -c " +
            shlex.quote("import numpy, scipy, cyton_sqi; print('PYNQ_RUNTIME_OK', numpy.__version__, scipy.__version__)") + "; "
            "curl -fsS http://127.0.0.1:9102/healthz"))
    finally:
        client.close()


if __name__ == "__main__":
    main()

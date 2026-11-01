import argparse
import shlex
import time
from pathlib import Path

import paramiko


HERE = Path(__file__).resolve().parent
REMOTE_DIR = "/home/xilinx/jupyter_notebooks/guardianloop_pynq"
FILES = (
    "window_server.py",
    "guardianloop_web.py",
)


def run(client, command, timeout=30):
    _, stdout, stderr = client.exec_command(command, timeout=timeout)
    output = stdout.read().decode("utf-8", errors="replace")
    errors = stderr.read().decode("utf-8", errors="replace")
    status = stdout.channel.recv_exit_status()
    if status:
        raise RuntimeError(f"command failed ({status}): {errors or output}")
    return output, errors


def main():
    parser = argparse.ArgumentParser(description="Deploy the offline replay dashboard bridge")
    parser.add_argument("--host", default="192.168.2.99")
    parser.add_argument("--user", default="xilinx")
    parser.add_argument("--password", default="xilinx")
    parser.add_argument("--token", required=True)
    parser.add_argument("--web-only", action="store_true",
                        help="update only the dashboard without resetting PL calibration")
    args = parser.parse_args()

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(args.host, username=args.user, password=args.password, timeout=10)
    try:
        stamp = time.strftime("%Y%m%d-%H%M%S")
        run(client, f"mkdir -p {REMOTE_DIR}")
        with client.open_sftp() as sftp:
            for name in (("guardianloop_web.py",) if args.web_only else FILES):
                source = HERE / name
                target = f"{REMOTE_DIR}/{name}"
                backup = f"{target}.before-replay-{stamp}"
                run(client, f"test ! -f {shlex.quote(target)} || cp -a {shlex.quote(target)} {shlex.quote(backup)}")
                staged = f"{target}.new"
                sftp.put(str(source), staged)
                try:
                    sftp.posix_rename(staged, target)
                except OSError:
                    sftp.remove(target)
                    sftp.rename(staged, target)
                print(f"deployed={target} backup={backup}")

        password = shlex.quote(args.password)
        token = shlex.quote(args.token)
        sudo_prefix = f"printf '%s\\n' {password} | sudo -S sh -c "
        run(client, sudo_prefix + shlex.quote(
            "systemctl stop guardianloop-cyton.service 2>/dev/null || true; "
            "systemctl restart guardianloop-web.service"
        ))
        if args.web_only:
            print("dashboard_restarted=true")
            return
        run(client, sudo_prefix + shlex.quote(
            "pkill -f '[w]indow_server.py' 2>/dev/null || true"
        ))
        run(client, sudo_prefix + shlex.quote(
            f"env XILINX_XRT=/usr GL_PYNQ_TOKEN={token} "
            f"nohup /usr/local/share/pynq-venv/bin/python3 {REMOTE_DIR}/window_server.py "
            ">/tmp/guardianloop-window-server.log 2>&1 </dev/null &"
        ))
        time.sleep(4)
        output, _ = run(
            client,
            "systemctl is-active guardianloop-web.service; "
            "systemctl is-active guardianloop-cyton.service || true; "
            "pgrep -af '[w]indow_server.py' || true; "
            "tail -n 20 /tmp/guardianloop-window-server.log || true",
        )
        print(output)
    finally:
        client.close()


if __name__ == "__main__":
    main()

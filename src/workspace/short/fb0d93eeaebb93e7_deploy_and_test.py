import argparse
from pathlib import Path

import paramiko


HERE = Path(__file__).resolve().parent
REMOTE_DIR = "/home/xilinx/jupyter_notebooks/z15_key_led"
FILES = (
    HERE / "output" / "z15_key_led.bit",
    HERE / "output" / "z15_key_led.hwh",
    HERE / "z15_key_led_test.py",
    HERE / "z15_key_led.ipynb",
)


def main():
    parser = argparse.ArgumentParser(description="Deploy and test the Z15 key/LED overlay")
    parser.add_argument("--host", default="192.168.2.99")
    parser.add_argument("--user", default="xilinx")
    parser.add_argument("--password", default="xilinx")
    args = parser.parse_args()
    missing = [str(path) for path in FILES if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"Missing deployment file(s): {missing}")

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(args.host, username=args.user, password=args.password, timeout=10)
    try:
        _, stdout, stderr = client.exec_command(f"mkdir -p {REMOTE_DIR}")
        if stdout.channel.recv_exit_status() != 0:
            raise RuntimeError(stderr.read().decode("utf-8", errors="replace"))
        with client.open_sftp() as sftp:
            for local_path in FILES:
                remote_path = f"{REMOTE_DIR}/{local_path.name}"
                sftp.put(str(local_path), remote_path)
                print(f"uploaded={remote_path}")

        remote_test = f"{REMOTE_DIR}/z15_key_led_test.py"
        command = (
            f"printf '%s\\n' {args.password} | sudo -S env XILINX_XRT=/usr "
            f"/usr/local/share/pynq-venv/bin/python3 {remote_test}"
        )
        _, stdout, stderr = client.exec_command(command, timeout=60)
        out = stdout.read().decode("utf-8", errors="replace")
        err = stderr.read().decode("utf-8", errors="replace")
        exit_code = stdout.channel.recv_exit_status()
        if out:
            print(out, end="" if out.endswith("\n") else "\n")
        if err:
            print(err, end="" if err.endswith("\n") else "\n")
        print(f"remote_exit={exit_code}")
        if exit_code != 0:
            raise SystemExit(exit_code)
    finally:
        client.close()


if __name__ == "__main__":
    main()

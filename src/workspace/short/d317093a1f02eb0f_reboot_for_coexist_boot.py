"""Request one approved Z15 reboot; the operator interrupts U-Boot in XCOM."""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from run_soak_stage import connect, command  # noqa: E402


def main():
    client = connect()
    try:
        if command(client, "systemctl is-active guardianloop-cyton.service || true").strip() != "inactive":
            raise RuntimeError("Formal Cyton service must be inactive")
        if command(client, "lsmod | grep '^gldma_owner ' || true").strip():
            raise RuntimeError("DMA owner loaded; no automated reboot")
        if command(client, "sha256sum /boot/guardianloop_coexist_20260929.dtb").split()[0] != \
                "4f73625b330bf07367c64a8c418d5716776ca092551ef5eb323eca4a0146f47c":
            raise RuntimeError("Staged temporary FDT does not match")
        stdin, _, _ = client.exec_command("sudo -S -p '' systemctl reboot", timeout=5)
        stdin.write("xilinx\n")
        stdin.flush()
        time.sleep(1)
        print("REBOOT_REQUEST_SENT")
    finally:
        client.close()


if __name__ == "__main__":
    main()

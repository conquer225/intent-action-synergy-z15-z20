"""Reboot the Z15 after the approved DMA run; never hot-unload the owner."""

import sys
import time
from pathlib import Path


APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))
from run_soak_stage import connect, command  # noqa: E402
from deploy_ssvep_rail_coalesce import sudo  # noqa: E402


def main():
    client = connect()
    try:
        status = sudo(
            client,
            "/home/xilinx/guardianloop_coexist_candidate_20260929/gldma_status_arm_static",
        )
        if "state=2 ever_started=1" not in status:
            raise RuntimeError(f"Unexpected owner state: {status.strip()}")
        if command(client, "systemctl is-active guardianloop-cyton.service || true").strip() != "inactive":
            raise RuntimeError("Formal service must remain stopped")
        if command(client, "sha256sum /boot/image.ub").split()[0] != \
                "27ee421d07d70f972e8a3bca96e1bc7810e847be2da2360aa5c11d36c93e89b2":
            raise RuntimeError("Original boot image changed")
        stdin, _, _ = client.exec_command("sudo -S -p '' systemctl reboot", timeout=5)
        stdin.write("xilinx\n")
        stdin.flush()
        time.sleep(1)
        print("FULL_REBOOT_REQUEST_SENT")
    finally:
        client.close()


if __name__ == "__main__":
    main()

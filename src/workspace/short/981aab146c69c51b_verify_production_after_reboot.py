"""Read-only check that the original GuardianLoop PL is back after reboot."""

from pathlib import Path
import sys


APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))
sys.path.insert(0, str(APP / "pl_filter_candidate" / "kernel_owner"))

from run_soak_stage import connect, command  # noqa: E402
from recover_formal_overlay import PROD_BIT, EXPECTED_SHA256, remote_checked  # noqa: E402


def main():
    client = connect()
    try:
        if command(client, "test ! -e /proc/device-tree/amba/dma-owner@40410000 && "
                   "test ! -e /dev/guardianloop_dma_keeper && echo ORIGINAL_DT").strip() != "ORIGINAL_DT":
            raise RuntimeError("Candidate device tree or driver still present")
        if command(client, f"sha256sum {PROD_BIT}").split()[0] != EXPECTED_SHA256:
            raise RuntimeError("Production bitstream hash changed")
        script = (
            "from pynq import Overlay; "
            f"o=Overlay({PROD_BIT!r},download=False); "
            "d=o.guardianloop_eeg_de_accel_v0_0; "
            "h=o.guardianloop_hgb_accel_v0_0; "
            "print('DE_ID=%08X HGB_ID=%08X MODEL_ID=%08X' % "
            "(d.read(0x20),h.read(0x18),h.read(0x30)))"
        )
        output = remote_checked(client, script)
        print(output, end="")
        if "DE_ID=44453031 HGB_ID=48473031 MODEL_ID=50537911" not in output:
            raise RuntimeError("Production PL register signatures did not match")
    finally:
        client.close()


if __name__ == "__main__":
    main()

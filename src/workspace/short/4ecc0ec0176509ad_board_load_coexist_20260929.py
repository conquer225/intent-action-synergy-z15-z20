"""Load the staged coexistence PL temporarily and read only its ID registers."""

from pathlib import Path
import argparse
import sys


APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))
sys.path.insert(0, str(APP / "pl_filter_candidate" / "kernel_owner"))

from run_soak_stage import connect, command  # noqa: E402
from recover_formal_overlay import remote_checked  # noqa: E402


BIT = "/home/xilinx/guardianloop_coexist_candidate_20260929/guardianloop_bd_wrapper.bit"
EXPECTED = "f05626df1bf429442fd43d601c3435868ffc64473b4746f62290f5b98b100031"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--inspect-only", action="store_true")
    args = parser.parse_args()
    client = connect()
    try:
        if command(client, "systemctl is-active guardianloop-cyton.service || true").strip() != "inactive":
            raise RuntimeError("Formal service must be stopped")
        if command(client, "lsmod | grep '^gldma_owner ' || true").strip():
            raise RuntimeError("DMA owner is already loaded")
        command(client, "test -e /proc/device-tree/amba/dma-owner@40410000")
        if command(client, f"sha256sum {BIT}").split()[0] != EXPECTED:
            raise RuntimeError("Staged candidate bitstream checksum changed")
        prefix = f"o=Overlay({BIT!r},download={not args.inspect_only}); "
        script = (
            "from pynq import Overlay, MMIO; " + prefix +
            "f=MMIO(0x41200000,0x1000); "
            "d=o.guardianloop_eeg_de_accel_v0_0; "
            "h=o.guardianloop_hgb_accel_v0_0; "
            "print('FILTER_STATUS=%08X DE_ID=%08X HGB_ID=%08X MODEL_ID=%08X' % "
            "(f.read(8),d.read(0x20),h.read(0x18),h.read(0x30)))"
        )
        output = remote_checked(client, script)
        print(output, end="")
        if "FILTER_STATUS=50460001 DE_ID=44453031 HGB_ID=48473031 MODEL_ID=50537911" not in output:
            raise RuntimeError("PL register signatures do not match the reviewed candidate")
    finally:
        client.close()


if __name__ == "__main__":
    main()

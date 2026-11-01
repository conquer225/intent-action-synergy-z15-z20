"""Restore and verify the production PL after an authorized temporary board test."""

from pathlib import Path
import shlex
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from run_soak_stage import connect, command
from deploy_ssvep_rail_coalesce import sudo


PROD_BIT = "/home/xilinx/jupyter_notebooks/guardianloop_pynq/guardianloop_pynq.bit"
EXPECTED_SHA256 = "c39b891704471a712fb7be3591841af1dd6791387957b873b11450c99eca41ca"
CYTON_UNIT = "guardianloop-cyton.service"


def remote_checked(client, script):
    invocation = "env XILINX_XRT=/usr /usr/local/share/pynq-venv/bin/python3 -c " + shlex.quote(script)
    return sudo(client, invocation)


def main():
    client = connect()
    stopped = False
    try:
        digest = command(client, "sha256sum " + shlex.quote(PROD_BIT)).split()[0]
        if digest != EXPECTED_SHA256:
            raise RuntimeError("Production bitstream checksum changed; no PL action taken")
        absent = command(client,
                         "test ! -e /dev/guardianloop_dma_keeper && "
                         "test ! -d /sys/kernel/config/device-tree/overlays/gl_dma_test_20260929 "
                         "&& echo CANDIDATE_ABSENT")
        if "CANDIDATE_ABSENT" not in absent:
            raise RuntimeError("Candidate driver or DT overlay remains; no PL action taken")
        sudo(client, "systemctl stop " + CYTON_UNIT)
        stopped = True
        script = (
            "from pynq import Overlay; "
            f"o=Overlay({PROD_BIT!r},download=True); "
            "d=o.guardianloop_eeg_de_accel_v0_0; "
            "h=o.guardianloop_hgb_accel_v0_0; "
            "print('DE_ID=%08X HGB_ID=%08X MODEL_ID=%08X' % "
            "(d.read(0x20),h.read(0x18),h.read(0x30)))"
        )
        ids = remote_checked(client, script)
        print(ids, end="")
        if "DE_ID=44453031 HGB_ID=48473031 MODEL_ID=50537911" not in ids:
            raise RuntimeError("Production PL register IDs did not match")
    finally:
        if stopped:
            sudo(client, "systemctl start " + CYTON_UNIT)
        client.close()


if __name__ == "__main__":
    main()

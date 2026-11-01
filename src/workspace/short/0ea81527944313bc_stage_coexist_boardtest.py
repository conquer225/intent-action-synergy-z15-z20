"""Stage the coexistence board-test artifacts without installing or starting them."""

import hashlib
from pathlib import Path
import shlex
import sys


APP = Path(__file__).resolve().parents[1]
ROOT = APP.parent
sys.path.insert(0, str(APP))
from run_soak_stage import connect, command  # noqa: E402


REMOTE = "/home/xilinx/guardianloop_coexist_candidate_20260929"
BIT = ROOT / "gli26c" / "bit1"
INTEGRATED = APP / "output" / "pl_integrated_candidate_20260929"
REPLAY = APP / "output" / "pl_recorded_shadow_20260929"
OWNER = APP / "pl_filter_candidate" / "kernel_owner"
HERE = Path(__file__).resolve().parent

FILES = {
    "guardianloop_bd_wrapper.bit": BIT / "guardianloop_bd_wrapper.bit",
    "guardianloop_bd_wrapper.hwh": BIT / "guardianloop_bd_wrapper.hwh",
    "gldma_owner_coexist.ko": INTEGRATED / "gldma_owner_coexist.ko",
    "gldma_board_check_replay_arm_static": REPLAY / "gldma_board_check_replay_arm_static",
    "recorded_frames.bin": REPLAY / "recorded_cyton" / "recorded_frames.bin",
    "coexist_boot_node.dtbo": INTEGRATED / "coexist_boot_node.dtbo",
    "merged_fdt_offline.dtb": INTEGRATED / "merged_fdt_offline.dtb",
    "coexist_node.dtsi": OWNER / "coexist_node.dtsi",
    "guardianloop-cyton-pl.service": HERE / "guardianloop-cyton-pl.service",
}
EXPECTED = {
    "guardianloop_bd_wrapper.bit": "f05626df1bf429442fd43d601c3435868ffc64473b4746f62290f5b98b100031",
    "guardianloop_bd_wrapper.hwh": "55d9e51f8c39da4605a97e5b2af67f91277a2892294f68fd89282e8c230c2653",
    "gldma_owner_coexist.ko": "97b9e91956ff904ff93f4f89761cd07c2414135f4b2594d6715ba0b82ffee06d",
    "recorded_frames.bin": "0a536da1a811ccd915c24ea443d9d0eaa40bb8ef5514692276288621ebae9dc2",
    "coexist_boot_node.dtbo": "f0206d96a0db9cafa69ab8d2f149a70ffac992fc95824561bfc08c3bc1ac1718",
    "merged_fdt_offline.dtb": "4f73625b330bf07367c64a8c418d5716776ca092551ef5eb323eca4a0146f47c",
}


def digest(path):
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def main():
    hashes = {name: digest(path) for name, path in FILES.items()}
    for name, expected in EXPECTED.items():
        if hashes[name] != expected:
            raise RuntimeError(f"Local artifact mismatch: {name}")

    client = connect()
    try:
        if command(client, "systemctl is-active guardianloop-cyton.service || true").strip() != "inactive":
            raise RuntimeError("Formal Cyton service must be inactive")
        if command(client, "lsmod | grep '^gldma_owner ' || true").strip():
            raise RuntimeError("A gldma_owner module is already loaded")
        command(client, "test ! -e " + shlex.quote(REMOTE))
        command(client, "mkdir -- " + shlex.quote(REMOTE))
        with client.open_sftp() as sftp:
            for name, path in FILES.items():
                remote_path = REMOTE + "/" + name
                sftp.put(str(path), remote_path)
                sftp.chmod(remote_path, 0o755 if name == "gldma_board_check_replay_arm_static" else 0o644)
                actual = command(client, "sha256sum " + shlex.quote(remote_path)).split()[0]
                if actual != hashes[name]:
                    raise RuntimeError(f"Remote artifact mismatch: {name}")
                print(f"STAGED {name} sha256={actual}")
        print(command(client, shlex.quote(REMOTE + "/gldma_board_check_replay_arm_static")
                      + " --check-vectors " + shlex.quote(REMOTE + "/recorded_frames.bin")), end="")
        print("STAGING_ONLY_NO_MODULE_OR_DMA")
    finally:
        client.close()


if __name__ == "__main__":
    main()

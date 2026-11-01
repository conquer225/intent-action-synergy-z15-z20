"""Stage an isolated PL-capable replay; do not alter production source or services."""

import hashlib
from pathlib import Path
import shlex
import sys


APP = Path(__file__).resolve().parents[1]
ROOT = APP.parent
sys.path.insert(0, str(APP))
from run_soak_stage import connect, command  # noqa: E402


REMOTE = "/home/xilinx/guardianloop_pl_service_candidate_20260929"
PROD = "/home/xilinx/jupyter_notebooks/guardianloop_pynq"
FILES = {
    "cyton_guardianloop.py": ROOT / "pynq_guardianloop" / "cyton_guardianloop.py",
    "pl_causal_filter.py": ROOT / "pynq_guardianloop" / "pl_causal_filter.py",
    "soak_service_replay.py": ROOT / "pynq_guardianloop" / "soak_service_replay.py",
    "input.npz": APP / "output" / "board_pipeline_profile_20260926" / "input.npz",
}
ASSETS = (
    "gameemo_covariance_svm.npz",
    "cyton_fatigue_overlap4.json",
    "seed_shadow_weights.npz",
    "ssvep_causal_protocol.json",
    "ssvep_candidate_sos.npy",
    "gameemo_emotion_model.json",
)


def main():
    client = connect()
    try:
        command(client, "test ! -e " + shlex.quote(REMOTE))
        command(client, "mkdir -- " + shlex.quote(REMOTE))
        with client.open_sftp() as sftp:
            for name, path in FILES.items():
                destination = REMOTE + "/" + name
                sftp.put(str(path), destination)
                local_hash = hashlib.sha256(path.read_bytes()).hexdigest()
                remote_hash = command(client, "sha256sum " + shlex.quote(destination)).split()[0]
                if local_hash != remote_hash:
                    raise RuntimeError(f"Staged file hash mismatch: {name}")
                print(f"STAGED {name} sha256={remote_hash}")
        for name in ASSETS:
            command(client, "test -f " + shlex.quote(PROD + "/" + name))
            command(client, "ln -s -- " + shlex.quote(PROD + "/" + name) +
                    " " + shlex.quote(REMOTE + "/" + name))
        print("ISOLATED_REPLAY_STAGED; production files and services unchanged")
    finally:
        client.close()


if __name__ == "__main__":
    main()

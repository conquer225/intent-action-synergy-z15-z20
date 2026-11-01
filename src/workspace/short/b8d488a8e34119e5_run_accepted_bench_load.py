"""Paced, isolated bench-recording load on Z15; never touches live USB or PL."""
import hashlib
import json
from pathlib import Path
import shlex
import time

import numpy as np

from run_soak_stage import ROOT, PROD, connect


SOURCE = Path(r"C:\Users\lenovo\Documents\OpenBCI_GUI\Recordings\OpenBCISession_2026-09-20_20-48-08\OpenBCI-RAW-2026-09-20_20-49-33.txt")
OUT = ROOT / "eeg_apps_z15/output/accepted_bench_load_20260927"
PYTHON = "/usr/local/share/pynq-venv/bin/python3"
SECONDS = 156


def remote(client, command, timeout=240):
    _, stdout, stderr = client.exec_command(command, timeout=timeout)
    output = stdout.read().decode(errors="replace") + stderr.read().decode(errors="replace")
    status = stdout.channel.recv_exit_status()
    if status:
        raise RuntimeError(f"exit={status}: {output[-3000:]}")
    return output


def sha(path):
    with Path(path).open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def main():
    if OUT.exists():
        raise RuntimeError("Output already exists; preserve prior evidence")
    OUT.mkdir(parents=True)
    n = SECONDS * 250
    data = np.loadtxt(SOURCE, delimiter=",", skiprows=5, usecols=range(9), max_rows=n)
    assert data.shape == (n, 9)
    seq = data[:, 0].astype(np.uint8)
    values = data[:, 1:9].astype(np.float64)
    assert np.isfinite(values).all()
    np.savez_compressed(OUT / "bench_input.npz", recorded=values, recorded_seq=seq)
    manifest = {"source_kind": "2026-09-20 non-wear bench recording; NOT human EEG",
                "source": str(SOURCE), "source_sha256": sha(SOURCE),
                "input_sha256": sha(OUT / "bench_input.npz"),
                "samples": n, "seconds": SECONDS,
                "sequence_discontinuities": int(np.count_nonzero(np.diff(seq.astype(int)) % 256 != 1)),
                "scope": "Isolated 250 Hz replay through current production ARM code; no live USB, PL, or service modifications."}
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    client = connect()
    stage = "/home/xilinx/jupyter_notebooks/accepted_bench_load_" + time.strftime("%Y%m%d-%H%M%S")
    try:
        manifest["production_before"] = remote(client, "systemctl show guardianloop-cyton guardianloop-web -p MainPID -p NRestarts -p ActiveState")
        manifest["production_hashes"] = remote(client, "sha256sum " + " ".join(PROD + "/" + name for name in
            ("cyton_guardianloop.py", "cyton_sqi.py", "seed_shadow.py", "ssvep_shadow.py",
             "guardianloop_pynq.bit", "guardianloop_pynq.hwh")))
        with client.open_sftp() as sftp:
            sftp.mkdir(stage)
            sftp.put(str(ROOT / "pynq_guardianloop/soak_service_replay.py"), stage + "/soak_service_replay.py")
            sftp.put(str(OUT / "bench_input.npz"), stage + "/input.npz")
        manifest["stage"] = stage
        (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        print("BENCH_REPLAY_START", flush=True)
        command = ("cd " + shlex.quote(stage) + " && timeout -s TERM -k 5 205 env "
                   "PYTHONPATH=" + shlex.quote(PROD) + " OPENBLAS_NUM_THREADS=1 XILINX_XRT=/usr "
                   + PYTHON + " soak_service_replay.py --input input.npz --input-kind recorded "
                   "--output bench-result --seconds " + str(SECONDS))
        print(remote(client, command), flush=True)
        with client.open_sftp() as sftp:
            for name in ("report.json", "producer.json", "monitor.jsonl", "primary_results.json",
                         "status.json", "shadow.json", "ssvep.json", "offline-replay.log"):
                try:
                    sftp.get(stage + "/bench-result/" + name, str(OUT / name))
                except FileNotFoundError:
                    pass
        manifest["production_after"] = remote(client, "systemctl show guardianloop-cyton guardianloop-web -p MainPID -p NRestarts -p ActiveState")
        manifest["production_hashes_after"] = remote(client, "sha256sum " + " ".join(PROD + "/" + name for name in
            ("cyton_guardianloop.py", "cyton_sqi.py", "seed_shadow.py", "ssvep_shadow.py",
             "guardianloop_pynq.bit", "guardianloop_pynq.hwh")))
        (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        report = json.loads((OUT / "report.json").read_text(encoding="utf-8"))
        print("BENCH_REPLAY_REPORT", json.dumps({key: report.get(key) for key in
            ("packets_consumed", "packets_expected", "packet_input_age_p95_ms",
             "packet_input_age_max_ms", "parent_cpu_seconds", "children_cpu_seconds",
             "parent_peak_rss_kib", "packet_compute_p95_ms", "packet_compute_p99_ms",
             "packet_compute_max_ms", "monitor_errors", "error")}), flush=True)
    finally:
        client.close()


if __name__ == "__main__":
    main()

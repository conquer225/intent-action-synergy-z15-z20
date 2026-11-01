"""Stage isolated playback sources and prepare board-only video copies."""
import argparse
import hashlib
import json
from pathlib import Path
import shlex
import uuid

import stage_server as upload

ROOT = Path(__file__).resolve().parent
STATE = ROOT / "playback_state.json"


def stage(client):
    if STATE.exists():
        raise RuntimeError("Inspect retained playback state before staging again")
    uploaded = json.loads(upload.STATE.read_text(encoding="utf-8"))
    remote = uploaded["remote"] + "/playback-" + uuid.uuid4().hex[:6]
    original = "/home/xilinx/jupyter_notebooks/guardianloop_pynq/guardianloop_pynq.bit"
    state = {"remote": remote, "prefix": remote.rsplit("/", 1)[-1],
        "source": uploaded["remote"] + "/uploads/d87609d9be1c4738ba9dc378438d9935.mp4",
        "source_sha256": "3fe1eacc6f3472327359dcb667e44fea59f099b5dd1e223eded48efccca43434",
        "original_overlay": original, "display_overlay": "/home/xilinx/tobii_z15/overlay/eye_wifi.bit",
        "display_root": "/home/xilinx/tobii_z15",
        "before_services": upload.trial.services(client),
        "before_hashes": upload.trial.protected(client)}
    upload.trial.execute(client, "mkdir -m 700 " + shlex.quote(remote))
    with client.open_sftp() as sftp:
        for name in ("transcode_video.c", "frame_decoder.c", "prepare_playback.py", "bench_decoder.py"):
            sftp.put(str(ROOT / name), remote + "/" + name)
            sftp.chmod(remote + "/" + name, 0o600)
            actual = upload.trial.execute(client, "sha256sum " + shlex.quote(remote + "/" + name)).split()[0]
            if actual != hashlib.sha256((ROOT / name).read_bytes()).hexdigest():
                raise RuntimeError("Staged source hash mismatch")
        with sftp.open(remote + "/playback_state.json", "wx") as handle:
            handle.write(json.dumps(state))
        sftp.chmod(remote + "/playback_state.json", 0o600)
    STATE.write_text(json.dumps(state, indent=2), encoding="utf-8")
    flags = " -O3 -mcpu=cortex-a9 -mfpu=neon -Wall -Wextra -Werror -I/usr/include/arm-linux-gnueabihf "
    libs = " -lavformat -lavcodec -lavutil -lswscale"
    print(upload.trial.execute(client, "gcc" + flags + shlex.quote(remote + "/transcode_video.c") +
        " -o " + shlex.quote(remote + "/transcode_video") + libs))
    print(upload.trial.execute(client, "gcc" + flags + " -fPIC -shared " + shlex.quote(remote + "/frame_decoder.c") +
        " -o " + shlex.quote(remote + "/frame_decoder.so") + libs))
    unit = state["prefix"] + "-convert"
    print(upload.trial.execute(client, "systemd-run --unit=" + unit + " --uid=xilinx "
        "--property=RuntimeMaxSec=300s --property=TimeoutStopSec=5s --property=MemoryMax=384M "
        "--property=CPUQuota=140% --property=Nice=8 --property=LimitCORE=0 "
        "/usr/bin/python3 " + shlex.quote(remote + "/prepare_playback.py"), root=True))
    print("PLAYBACK_PREPARATION_STARTED " + remote, flush=True)


def start_display(client, state):
    remote = state["remote"]
    pynq_python = "/usr/local/share/pynq-venv/bin/python3"
    if state.get("hardware_started"):
        status = upload.trial.execute(client, "systemctl show " + state["hardware_unit"] +
            " -p MainPID -p Result")
        if "MainPID=0" not in status or "Result=exit-code" not in status:
            raise RuntimeError("Previous display test is not an inspected failed attempt")
        query = "from pynq import PL; print(PL.bitfile_name)"
        current = upload.trial.execute(client, "env XILINX_XRT=/usr " + pynq_python +
            " -c " + shlex.quote(query), root=True).strip()
        if current != state["original_overlay"]:
            raise RuntimeError("Previous display attempt has not restored original PL")
        timer = state.get("recovery_timer", state["prefix"] + "-display-restore.timer")
        loaded = upload.trial.execute(client, "systemctl show " + timer + " -p LoadState --value").strip()
        if loaded != "not-found":
            upload.trial.execute(client, "systemctl stop " + timer, root=True)
        state.setdefault("previous_display_attempts", []).append({"unit": state["hardware_unit"],
            "status": status, "original_pl_confirmed": True})
    output = upload.trial.execute(client, "cat " + shlex.quote(remote + "/conversion_report.json"))
    if not json.loads(output).get("original_preserved"):
        raise RuntimeError("Board-only preparation did not retain the original")
    paths = [state["original_overlay"], state["original_overlay"].rsplit(".", 1)[0] + ".hwh",
             state["display_overlay"], state["display_overlay"].rsplit(".", 1)[0] + ".hwh"]
    hashes = {}
    for path in paths:
        hashes[path] = upload.trial.execute(client, "sha256sum " + shlex.quote(path)).split()[0]
    if hashes[state["display_overlay"]] != "8b52892466a1b4d025c5c693a951727ae6215e57ca3e5fa0dedaa2a1d510d50f" or \
       hashes[paths[3]] != "5dcfe537c6793f5b18b47550f73078ab8d73500888e585037a707c8be1ebacef":
        raise RuntimeError("Display pair differs from the previously audited board copy")
    for path in paths[:2]:
        backup = remote + "/" + Path(path).name
        upload.trial.execute(client, "cp -n -- " + shlex.quote(path) + " " + shlex.quote(backup))
        if upload.trial.execute(client, "sha256sum " + shlex.quote(backup)).split()[0] != hashes[path]:
            raise RuntimeError("Recovery copy checksum mismatch")
    display_lib = state["display_root"] + "/libtobii_display.so"
    upload.trial.execute(client, "cp -n -- " + shlex.quote(display_lib) + " " + shlex.quote(remote + "/libtobii_display.so"))
    if upload.trial.execute(client, "sha256sum " + shlex.quote(display_lib)).split()[0] != \
       upload.trial.execute(client, "sha256sum " + shlex.quote(remote + "/libtobii_display.so")).split()[0]:
        raise RuntimeError("Display library copy mismatch")
    state["hardware_hashes"] = hashes
    hardware_prefix = state["prefix"] + "-h" + uuid.uuid4().hex[:4]
    state["hardware_unit"] = hardware_prefix + "-display.service"
    state["recovery_timer"] = hardware_prefix + "-display-restore.timer"
    with client.open_sftp() as sftp:
        for name in ("display_trial.py", "playback_recovery.py"):
            sftp.put(str(ROOT / name), remote + "/" + name)
            sftp.chmod(remote + "/" + name, 0o600)
            if upload.trial.execute(client, "sha256sum " + shlex.quote(remote + "/" + name)).split()[0] != \
               hashlib.sha256((ROOT / name).read_bytes()).hexdigest():
                raise RuntimeError("Display source transfer mismatch")
        with sftp.open(remote + "/playback_state.json", "w") as handle:
            handle.write(json.dumps(state))
    STATE.write_text(json.dumps(state, indent=2), encoding="utf-8")
    print(upload.trial.execute(client, "systemd-run --unit=" + hardware_prefix + "-display-restore "
        "--on-active=150s --timer-property=AccuracySec=1s env XILINX_XRT=/usr " + pynq_python + " " +
        shlex.quote(remote + "/playback_recovery.py"), root=True))
    print(upload.trial.execute(client, "systemd-run --unit=" + state["hardware_unit"] +
        " --property=TimeoutStopSec=infinity --property=KillMode=process --property=LimitCORE=0 "
        "env XILINX_XRT=/usr " + pynq_python + " " + shlex.quote(remote + "/display_trial.py"), root=True))
    state["hardware_started"] = True
    STATE.write_text(json.dumps(state, indent=2), encoding="utf-8")
    print("FINITE_HDMI_TEST_DISPATCHED", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("stage", "status", "bench", "display", "display-status"))
    args = parser.parse_args()
    client = upload.trial.connect("192.168.2.99")
    try:
        if args.action == "stage":
            stage(client)
        else:
            state = json.loads(STATE.read_text(encoding="utf-8"))
            remote = state["remote"]
            if args.action == "display":
                start_display(client, state)
            elif args.action == "display-status":
                print(upload.trial.execute(client, "systemctl show " + state["hardware_unit"] +
                    " -p ActiveState -p Result -p MainPID -p ExecMainStatus; journalctl -u " +
                    state["hardware_unit"] + " --no-pager -n 5"))
            elif args.action == "status":
                print(upload.trial.execute(client, "systemctl show " + state["prefix"] + "-convert "
                    "-p ActiveState -p Result -p ExecMainStatus; journalctl -u " + state["prefix"] +
                    "-convert --no-pager -n 6"))
            else:
                print(upload.trial.execute(client, "timeout 30s /usr/bin/python3 " +
                    shlex.quote(remote + "/bench_decoder.py")))
            print("PROTECTED_UNCHANGED " + str(upload.trial.protected(client) == state["before_hashes"]))
    finally:
        client.close()

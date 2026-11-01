"""Deploy a private upload trial, reusing the existing scoped network helpers."""
import argparse
import hashlib
import http.client
import ipaddress
import json
from pathlib import Path
import secrets
import sys
import time
from urllib.parse import quote
import uuid
import zlib

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent / "dlna_receiver_20261007"))
import run_test as trial

STATE = ROOT / "stage.json"
DECODER = "/home/xilinx/gl-video-7498b9dd4f/video_decode_native_probe"


def save(state):
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def request(state, method, path, data=None, extra=None):
    client = http.client.HTTPConnection("192.168.2.99", 9117, timeout=30)
    headers = {"X-Media-Key": state["key"]}
    headers.update(extra or {})
    try:
        client.request(method, path, data, headers)
        response = client.getresponse()
        body = json.loads(response.read())
        if response.status not in {200, 201}:
            raise RuntimeError("HTTP %d: %s" % (response.status, body.get("error", "")))
        return body
    finally:
        client.close()


def start_server(client, state):
    remote, unit = state["remote"], state["server_unit"]
    loaded = trial.execute(client, "systemctl show " + unit + " -p LoadState --value").strip()
    if loaded == "not-found":
        trial.execute(client, "systemd-run --unit=" + unit + " --uid=xilinx "
                      "--property=RuntimeMaxSec=35min --property=TimeoutStopSec=5s --property=LimitCORE=0 "
                      "--property=MemoryMax=512M /usr/bin/python3 " + remote + "/upload_server.py "
                      "--store " + remote + "/uploads --key-file " + remote + "/access.key --decoder " + DECODER, root=True)
    elif trial.execute(client, "systemctl show " + unit + " -p ActiveState --value").strip() != "active":
        trial.execute(client, "systemctl start " + unit, root=True)
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        try:
            health = request(state, "GET", "/health")
        except (OSError, http.client.HTTPException):
            time.sleep(.5)
        else:
            if health.get("upload_ready"):
                return
    raise RuntimeError("Upload server did not become ready")


def prepare(client):
    if STATE.exists():
        raise RuntimeError("Inspect the existing trial before deploying another")
    if trial.execute(client, "test -x " + DECODER + " && echo ready").strip() != "ready":
        raise RuntimeError("Existing native decoder is unavailable")
    remote = "/home/xilinx/gl-file-video-" + uuid.uuid4().hex[:10]
    old_trial = json.loads(trial.STATE_PATH.read_text())
    state = {"remote": remote, "prefix": remote.rsplit("/", 1)[-1],
             "server_unit": remote.rsplit("/", 1)[-1] + "-upload",
             "key": secrets.token_hex(12), "decoder": DECODER,
             "ap_helper": old_trial["remote"] + "/board_control.py",
             "before_hashes": trial.protected(client), "before_services": trial.services(client)}
    trial.execute(client, "mkdir -m 700 " + remote)
    save(state)
    with client.open_sftp() as sftp:
        for name in ("upload_server.py", "upload.html", "decode_worker.py", "restore_network.py", "test_upload.py"):
            sftp.put(str(ROOT / name), remote + "/" + name)
            sftp.chmod(remote + "/" + name, 0o600)
            if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != trial.execute(client, "sha256sum " + remote + "/" + name).split()[0]:
                raise RuntimeError("Source transfer hash mismatch")
        with sftp.open(remote + "/access.key", "wx") as handle:
            handle.write(state["key"])
        sftp.chmod(remote + "/access.key", 0o600)
        with sftp.open(remote + "/state.json", "wx") as handle:
            handle.write(json.dumps(state))
        sftp.chmod(remote + "/state.json", 0o600)
    tests = trial.execute(client, "cd " + remote + " && /usr/bin/python3 -m unittest -q test_upload 2>&1")
    if "Ran 10 tests" not in tests or "OK" not in tests:
        raise RuntimeError("Board upload regression tests did not pass")
    print("BOARD_UPLOAD_TESTS_PASSED count=10", flush=True)
    start_server(client, state)
    state["prepared"] = True
    save(state)
    print("ISOLATED_UPLOAD_READY", flush=True)


def selftest(client, state):
    if state.get("selftest"):
        raise RuntimeError("The retained self-test must not be uploaded repeatedly")
    with client.open_sftp() as sftp:
        with sftp.open("/home/xilinx/gl-video-7498b9dd4f/720p30_bitrate4m.mp4", "rb") as handle:
            sample = handle.read()
    result = request(state, "POST", "/upload", sample, {
        "X-File-Name": quote("板端软件自检样本-非手机文件.mp4"),
        "X-File-CRC32": "%08x" % (zlib.crc32(sample) & 0xffffffff), "Content-Type": "video/mp4"})
    if result["sha256"] != hashlib.sha256(sample).hexdigest():
        raise RuntimeError("End-to-end sample hash mismatch")
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        items = request(state, "GET", "/status")["files"]
        item = next(item for item in items if item["id"] == result["id"])
        if item["decode_state"] in {"passed", "failed"}:
            break
        time.sleep(1)
    else:
        raise RuntimeError("Native decode result did not complete")
    state["selftest"] = item
    save(state)
    if item["decode_state"] != "passed":
        raise RuntimeError("Board decode check failed")
    if trial.protected(client) != state["before_hashes"] or trial.services(client) != state["before_services"]:
        raise RuntimeError("Formal runtime changed during self-test")
    print(json.dumps({"selftest": item["decode"], "sha256_matched": True, "phone_file": False,
                      "formal_unchanged": True, "hdmi_verified": False}), flush=True)


def hotspot(client, state):
    if not state.get("selftest") or state["selftest"]["decode_state"] != "passed":
        raise RuntimeError("Board self-test must pass first")
    if state.get("hotspot_started"):
        raise RuntimeError("Inspect the running trial instead of starting a second one")
    network = trial.execute(client, "ip -br addr; iw dev wlan0 info")
    if "192.168.2.99/24" not in network or "192.168.50.1/24" not in network or "type AP" not in network:
        raise RuntimeError("Expected wired control and original AP are unavailable")
    trial.stop_timer(client, state["prefix"])
    state["prefix"] = state["remote"].rsplit("/", 1)[-1] + "-n" + uuid.uuid4().hex[:6]
    state.setdefault("server_unit", state["remote"].rsplit("/", 1)[-1] + "-upload")
    save(state)
    start_server(client, state)
    remote, prefix = state["remote"], state["prefix"]
    with client.open_sftp() as sftp:
        with sftp.open(trial.SAVED_NETWORK) as handle:
            station = handle.read().decode()
        if 'ssid="QqqQ"' not in station:
            raise RuntimeError("Saved hotspot is not QqqQ")
        station = "\n".join("ctrl_interface=" + remote + "/control" if line.startswith("ctrl_interface=") else line
                            for line in station.splitlines()) + "\n"
        state.update(ap_active=True, dhcp_active=True)
        files = {"network.py": trial.BOARD_PROGRAM, "dhcp_hook": trial.DHCP_HOOK,
                 "station.conf": station, "dhclient.conf": "timeout 25;\nretry 5;\nrequest subnet-mask, routers, domain-name-servers;\n",
                 "state.json": json.dumps(state)}
        try:
            sftp.stat(remote + "/lease.json")
        except FileNotFoundError:
            pass
        else:
            sftp.rename(remote + "/lease.json", remote + "/lease-before-" + prefix + ".json")
        for name, data in files.items():
            with sftp.open(remote + "/" + name, "w") as handle:
                handle.write(data)
            sftp.chmod(remote + "/" + name, 0o700 if name == "dhcp_hook" else 0o600)
    trial.execute(client, "systemd-run --unit=" + prefix + "-restore --on-active=30min --timer-property=AccuracySec=1s "
                  "/usr/bin/python3 " + remote + "/restore_network.py", root=True)
    try:
        trial.execute(client, "/usr/bin/python3 " + remote + "/network.py switch", root=True)
        deadline = time.monotonic() + 55
        while time.monotonic() < deadline:
            lease = trial.execute(client, "test -f " + remote + "/lease.json && cat " + remote + "/lease.json || true")
            if lease.strip():
                state["lease"] = json.loads(lease)
                break
            time.sleep(2)
        else:
            raise RuntimeError("Phone hotspot did not provide an address")
        address = str(ipaddress.IPv4Interface(state["lease"]["address"]).ip)
        state.update(board_ip=address, hotspot_started=True)
        save(state)
        trial.execute(client, "systemd-run --unit=" + prefix + "-guard /usr/bin/python3 " + remote + "/network.py guard", root=True)
        if trial.protected(client) != state["before_hashes"] or trial.services(client) != state["before_services"]:
            raise RuntimeError("Formal runtime changed during network test")
        print("PHONE_UPLOAD_URL http://" + address + ":9117/#" + state["key"], flush=True)
    except Exception:
        trial.execute(client, "/usr/bin/python3 " + remote + "/restore_network.py", root=True)
        trial.stop_timer(client, prefix)
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("prepare", "selftest", "hotspot", "status", "stop"))
    args = parser.parse_args()
    client = trial.connect("192.168.2.99")
    try:
        if args.action == "prepare":
            prepare(client)
        else:
            state = json.loads(STATE.read_text(encoding="utf-8"))
            if args.action == "selftest":
                selftest(client, state)
            elif args.action == "hotspot":
                hotspot(client, state)
            elif args.action == "status":
                print(json.dumps(request(state, "GET", "/status"), ensure_ascii=False))
                print("FORMAL_UNCHANGED " + str(trial.protected(client) == state["before_hashes"] and trial.services(client) == state["before_services"]))
            else:
                print(trial.execute(client, "/usr/bin/python3 " + state["remote"] + "/restore_network.py", root=True))
                trial.stop_timer(client, state["prefix"])
    finally:
        client.close()

"""Benchmark the current Wi-Fi and existing ARM decoder without changing formal runtime."""
import hashlib
import http.client
import json
from pathlib import Path
import socket
import subprocess
import time
import uuid

import numpy as np

from connect_phone_hotspot import execute, protected, profile, wifi_address
from reload_formal_wireless import netsh
from run_soak_stage import connect

ROOT = Path(__file__).resolve().parent
BOARD = "192.168.43.6"
PORT = 9118


def network_test(pc_address, direction, seconds=10, rate=None):
    size = 262144 if rate is None else 32768
    payload = (bytes(range(251)) * 1045)[:size]
    conn = http.client.HTTPConnection(BOARD, PORT, timeout=5, source_address=(str(pc_address), 0))
    conn.connect()
    conn.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    samples = []
    transferred = 0
    start = time.perf_counter()
    try:
        while time.perf_counter() - start < seconds:
            if rate:
                due = start + transferred * 8 / (rate * 1e6)
                if due > time.perf_counter():
                    time.sleep(due - time.perf_counter())
            a = time.perf_counter()
            conn.request("POST" if direction == "upload" else "GET", "/" + direction,
                         body=payload if direction == "upload" else None)
            response = conn.getresponse()
            body = response.read()
            if response.status != 200:
                raise RuntimeError("Probe HTTP failure")
            if direction == "upload":
                if json.loads(body)["bytes"] != size:
                    raise RuntimeError("Receiver byte count mismatch")
                transferred += size
            else:
                if body != (bytes(range(251)) * 1045)[:262144]:
                    raise RuntimeError("Download payload corruption")
                transferred += len(body)
            samples.append((time.perf_counter() - a) * 1000)
    finally:
        conn.close()
    elapsed = time.perf_counter() - start
    return {"source": "PC Wi-Fi -> phone hotspot -> Z15 (two wireless hops)",
            "direction": direction, "duration_s": elapsed, "bytes": transferred,
            "mbps": transferred * 8 / elapsed / 1e6, "requests": len(samples),
            "request_p50_ms": float(np.percentile(samples, 50)),
            "request_p95_ms": float(np.percentile(samples, 95)),
            "request_max_ms": max(samples), "target_mbps": rate,
            "errors": 0, "transport": "persistent HTTP/1.1 over TCP; not iperf or video latency"}


def main():
    identifier = "gl-video-" + uuid.uuid4().hex[:10]
    remote = "/home/xilinx/" + identifier
    folder = ROOT / "output" / identifier
    folder.mkdir()
    client = connect("192.168.2.99")
    original = profile()
    report = {"remote": remote, "unit": identifier, "board_wifi": BOARD, "network": [],
              "scope": "network and ARM decoding only; no HDMI, no screen capture, no PL change"}
    try:
        report["before_hashes"] = protected(client)
        report["before_services"] = execute(client, "systemctl show guardianloop-web.service guardianloop-cyton.service -p Id -p MainPID -p NRestarts -p ActiveState")
        report["before_net_counters"] = execute(client, "cat /sys/class/net/wlan0/statistics/rx_bytes /sys/class/net/wlan0/statistics/tx_bytes")
        execute(client, "mkdir -m 700 " + remote)
        samples = json.loads((ROOT / "output/video_probe_motion_20261006/samples.json").read_text())
        with client.open_sftp() as sftp:
            for name in ["video_network_probe.py", "video_decode_probe.py"]:
                sftp.put(str(ROOT / name), remote + "/" + name)
            for sample in samples:
                source = Path(sample["path"])
                sftp.put(str(source), remote + "/" + source.name)
                received = execute(client, "sha256sum " + remote + "/" + source.name).split()[0]
                if received != sample["sha256"]:
                    raise RuntimeError("Video sample transfer integrity failed")
        report["samples"] = samples
        # Isolated server expires automatically; leaves installed services untouched.
        execute(client, "systemd-run --unit=" + identifier + " --uid=xilinx --property=RuntimeMaxSec=45min --property=TimeoutStopSec=5s /usr/bin/python3 " + remote + "/video_network_probe.py --bind " + BOARD + " --port " + str(PORT), True)
        print("PHONE_TEST_PAGE http://" + BOARD + ":" + str(PORT) + "/", flush=True)
        report["decode"] = []
        for repeat in range(2):
            results = []
            for sample in samples:
                command = "python3 " + remote + "/video_decode_probe.py " + remote + "/" + Path(sample["path"]).name
                output = execute(client, command)
                results.extend(json.loads(line) for line in output.splitlines() if line.startswith("{"))
            report["decode"].append(results)
            print("ARM_DECODE " + json.dumps(results, ensure_ascii=False), flush=True)
        netsh("QqqQ")
        for _ in range(30):
            try:
                if profile() == "QqqQ":
                    break
            except RuntimeError:
                pass
            time.sleep(.5)
        pc_address = wifi_address()
        if str(pc_address).rsplit(".", 1)[0] != "192.168.43":
            raise RuntimeError("PC hotspot network mismatch")
        report["pc_wifi_ip"] = str(pc_address)
        for direction in ["upload", "download"]:
            for repeat in range(3):
                result = network_test(pc_address, direction)
                result["repeat"] = repeat + 1
                report["network"].append(result)
                print("WIRELESS_TEST " + json.dumps(result), flush=True)
        for rate in [4, 8, 12]:
            result = network_test(pc_address, "upload", seconds=6, rate=rate)
            report["network"].append(result)
            print("PACED_UPLOAD " + json.dumps(result), flush=True)
        report["after_hashes"] = protected(client)
        report["protected_files_unchanged"] = report["before_hashes"] == report["after_hashes"]
        report["after_services"] = execute(client, "systemctl show guardianloop-web.service guardianloop-cyton.service -p Id -p MainPID -p NRestarts -p ActiveState")
        report["after_net_counters"] = execute(client, "cat /sys/class/net/wlan0/statistics/rx_bytes /sys/class/net/wlan0/statistics/tx_bytes; iw dev wlan0 link")
        print("PROTECTED_FILES_UNCHANGED " + str(report["protected_files_unchanged"]), flush=True)
    finally:
        netsh(original)
        client.close()
        (folder / "result.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
        print("PC_WIFI_RESTORE_REQUESTED " + original, flush=True)
        print("REPORT " + str(folder / "result.json"), flush=True)


if __name__ == "__main__":
    main()

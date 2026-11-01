"""Reversible, runtime-only Z15 station test; never edits the installed AP."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import getpass
import ipaddress
import json
import logging
from pathlib import Path
import re
import socket
import subprocess
import sys
import time
import uuid

import paramiko

from reload_formal_wireless import netsh, wait_board
from run_soak_stage import connect


BOARD_PROGRAM = r'''
import ipaddress, json, os, pathlib, subprocess, sys, time
base = pathlib.Path(__file__).resolve().parent
state = json.loads((base / "state.json").read_text())
prefix = state["prefix"]
def run(args, required=True):
    try:
        p = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                           universal_newlines=True, timeout=25)
    except subprocess.TimeoutExpired:
        if required:
            raise
        return "NETWORK_COMMAND_TIMED_OUT"
    if required and p.returncode:
        raise RuntimeError("network command failed: " + p.stdout[:500])
    return p.stdout
def rollback():
    for name in ("guard", "switch", "dhcp", "wpa"):
        if name != sys.argv[1]:
            run(["systemctl", "stop", prefix + "-" + name + ".service"], False)
    run(["systemctl", "stop", prefix + "-rollback.timer"], False)
    run(["ip", "route", "flush", "dev", "wlan0"], False)
    run(["ip", "addr", "flush", "dev", "wlan0"], False)
    run(["resolvectl", "revert", "wlan0"], False)
    run(["ip", "link", "set", "wlan0", "down"], False)
    run(["ip", "link", "set", "wlan0", "up"], False)
    if state["ap_active"]:
        run(["systemctl", "start", "guardianloop-ap.service"])
    if state["dhcp_active"]:
        run(["systemctl", "start", "guardianloop-dhcp.service"])
    (base / "rolled_back").touch(mode=0o600)
    print("ORIGINAL_AP_RESTORED", flush=True)
def switch():
    try:
        run(["systemctl", "stop", "guardianloop-dhcp.service", "guardianloop-ap.service"])
        run(["ip", "link", "set", "wlan0", "down"])
        run(["iw", "dev", "wlan0", "set", "type", "managed"])
        run(["ip", "link", "set", "wlan0", "up"])
        run(["systemd-run", "--unit=" + prefix + "-wpa", "--property=Restart=on-failure", "--property=TimeoutStopSec=5s",
             "/sbin/wpa_supplicant", "-i", "wlan0", "-D", "nl80211", "-c", str(base / "station.conf")])
        run(["systemd-run", "--unit=" + prefix + "-dhcp", "--property=TimeoutStopSec=5s", "/sbin/dhclient", "-d", "-1",
             "-cf", str(base / "dhclient.conf"), "-sf", str(base / "dhcp_hook"),
             "-pf", str(base / "dhclient.pid"), "-lf", str(base / "dhclient.leases"), "wlan0"])
    except Exception:
        rollback()
        raise
def guard():
    # Losing the phone must not strand the board after a successful test.
    bad_since = None
    while True:
        time.sleep(5)
        out = run(["/sbin/wpa_cli", "-p", str(base / "control"), "-i", "wlan0", "status"], False)
        if "wpa_state=COMPLETED" in out:
            bad_since = None
        else:
            bad_since = bad_since or time.monotonic()
            if time.monotonic() - bad_since > 90:
                rollback()
                break
action = sys.argv[1]
if action == "switch": switch()
elif action == "rollback": rollback()
elif action == "guard": guard()
else: raise ValueError("Unknown network action")
'''

DHCP_HOOK = r'''#!/usr/bin/python3
import ipaddress, json, os, pathlib, subprocess
base = pathlib.Path(__file__).resolve().parent
event = os.environ.get("reason", "")
def run(args):
    subprocess.run(args, check=True, timeout=8, stdout=subprocess.DEVNULL)
if event in {"BOUND", "RENEW", "REBIND", "REBOOT"}:
    addr = ipaddress.IPv4Interface(os.environ["new_ip_address"] + "/" + os.environ["new_subnet_mask"])
    routers = [str(ipaddress.IPv4Address(x)) for x in os.environ.get("new_routers", "").split()]
    dns = [str(ipaddress.IPv4Address(x)) for x in os.environ.get("new_domain_name_servers", "").split()]
    run(["/sbin/ip", "addr", "replace", str(addr), "dev", "wlan0"])
    if routers:
        run(["/sbin/ip", "route", "replace", "default", "via", routers[0], "dev", "wlan0", "metric", "650"])
    if dns:
        run(["/usr/bin/resolvectl", "dns", "wlan0"] + dns)
        run(["/usr/bin/resolvectl", "domain", "wlan0", "~."])
    (base / "lease.json").write_text(json.dumps({"address": str(addr), "routers": routers, "dns": dns}))
elif event in {"EXPIRE", "FAIL", "RELEASE", "STOP"}:
    subprocess.run(["/sbin/ip", "route", "flush", "dev", "wlan0"], timeout=8)
    subprocess.run(["/sbin/ip", "addr", "flush", "dev", "wlan0"], timeout=8)
    subprocess.run(["/usr/bin/resolvectl", "revert", "wlan0"], timeout=8)
'''


def execute(client, command, root=False):
    stdin, stdout, stderr = client.exec_command(
        "sudo -S -p '' -- " + command if root else command, timeout=35)
    if root:
        stdin.write(client.get_transport().auth_handler.password + "\n")
        stdin.flush()
    out = stdout.read().decode(errors="replace")
    err = stderr.read().decode(errors="replace")
    if stdout.channel.recv_exit_status():
        raise RuntimeError(err[:500] + out[:500])
    return out


def profile():
    out = subprocess.check_output(["netsh", "wlan", "show", "interfaces"]).decode(errors="replace")
    match = re.search(r"^\s*Profile\s*:\s*(.+?)\s*$", out, re.M)
    if not match:
        raise RuntimeError("Cannot identify original PC Wi-Fi")
    return match.group(1)


def wifi_address():
    for _ in range(30):
        out = subprocess.check_output(["powershell", "-NoProfile", "-Command",
            "Get-NetIPAddress -InterfaceAlias WLAN -AddressFamily IPv4 | Select-Object -ExpandProperty IPAddress"]).decode().strip()
        for line in out.splitlines():
            address = ipaddress.IPv4Address(line.strip())
            if address.is_private and not address.is_link_local and not address.is_loopback:
                return address
        time.sleep(.5)
    raise RuntimeError("PC did not obtain a hotspot address")


def find_board(addresses, pc_ip, host_key):
    logger = logging.getLogger("hotspot.discovery")
    logger.addHandler(logging.NullHandler())
    logger.propagate = False
    def probe(address):
        if address == pc_ip:
            return None
        transport = None
        try:
            sock = socket.create_connection((str(address), 22), timeout=.35)
            transport = paramiko.Transport(sock)
            transport.set_log_channel("hotspot.discovery")
            transport.banner_timeout = 1
            transport.start_client(timeout=1)
            if transport.get_remote_server_key().asbytes() == host_key:
                return str(address)
        except (OSError, paramiko.SSHException, EOFError):
            return None
        finally:
            if transport is not None:
                transport.close()
    # Restrict discovery to the phone's actual /24, pinning the board SSH identity.
    with ThreadPoolExecutor(max_workers=24) as pool:
        return next((x for x in pool.map(probe, addresses) if x), None)


def protected(client):
    paths = ["/etc/systemd/system/guardianloop-ap.service", "/etc/systemd/system/guardianloop-dhcp.service",
             "/etc/systemd/system/guardianloop-web.service", "/etc/systemd/system/guardianloop-cyton.service",
             "/etc/NetworkManager/conf.d/99-guardianloop-wlan0-unmanaged.conf", "/boot/boot.scr", "/boot/image.ub",
             "/home/xilinx/jupyter_notebooks/guardianloop_pynq/release_manifest.json"]
    return execute(client, "sha256sum " + " ".join(paths))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ssid", required=True)
    parser.add_argument("--wired", action="store_true")
    parser.add_argument("--saved-profile", action="store_true")
    args = parser.parse_args()
    if args.saved_profile:
        saved = subprocess.check_output(["netsh", "wlan", "show", "profile",
                                         "name=" + args.ssid, "key=clear"]).decode(errors="replace")
        key = re.search(r"^\s*Key Content\s*:\s*(.+?)\s*$", saved, re.M)
        if not key:
            raise RuntimeError("Saved hotspot credential unavailable")
        password = key.group(1)
        saved = ""
        key = None
    else:
        password = getpass.getpass("Hotspot password (not echoed): ")
    if not 8 <= len(password) <= 63 or any(x in args.ssid for x in '\n\r"\\'):
        raise ValueError("Invalid hotspot credentials")
    original = profile()
    identifier = "gl-phone-" + uuid.uuid4().hex[:10]
    remote = "/home/xilinx/" + identifier
    report = {"ssid": args.ssid, "temporary": True, "remote": remote, "prefix": identifier}
    folder = Path(__file__).parent / "output" / identifier
    folder.mkdir()
    client = None
    try:
        if not args.wired:
            netsh("GuardianLoop-Z15")
            wait_board()
        client = connect("192.168.2.99" if args.wired else "192.168.50.1")
        host_key = client.get_transport().get_remote_server_key().asbytes()
        report["before_hashes"] = protected(client)
        report["before_services"] = execute(client, "systemctl show guardianloop-web.service guardianloop-cyton.service -p Id -p MainPID -p NRestarts -p ActiveState")
        report["boot_id"] = execute(client, "cat /proc/sys/kernel/random/boot_id").strip()
        # Never transmit the supplied passphrase in a command or save it in a report.
        psk = hashlib.pbkdf2_hmac("sha1", password.encode(), args.ssid.encode(), 4096, 32).hex()
        password = ""
        execute(client, "mkdir -m 700 " + remote)
        config = ('ctrl_interface=' + remote + '/control\nnetwork={\n    ssid="' + args.ssid + '"\n'
                  '    psk=' + psk + '\n    key_mgmt=WPA-PSK\n}\n')
        files = {"network.py": BOARD_PROGRAM, "dhcp_hook": DHCP_HOOK, "station.conf": config,
                 "dhclient.conf": "timeout 25;\nretry 5;\nrequest subnet-mask, routers, domain-name-servers;\n",
                 "state.json": json.dumps({"prefix": identifier, "ap_active": True, "dhcp_active": True})}
        with client.open_sftp() as sftp:
            for name, content in files.items():
                with sftp.open(remote + "/" + name, "wx") as stream:
                    stream.write(content)
                sftp.chmod(remote + "/" + name, 0o700 if name == "dhcp_hook" else 0o600)
        execute(client, "systemd-run --unit=" + identifier + "-rollback --on-active=6min --timer-property=AccuracySec=1s /usr/bin/python3 " + remote + "/network.py rollback", True)
        execute(client, "systemd-run --unit=" + identifier + "-switch --on-active=2s --timer-property=AccuracySec=1s /usr/bin/python3 " + remote + "/network.py switch", True)
        print("SWITCH_SCHEDULED_WITH_ROLLBACK " + remote, flush=True)
        if args.wired:
            deadline = time.monotonic() + 65
            while time.monotonic() < deadline:
                ready = execute(client, "test -f " + remote + "/lease.json && cat " + remote + "/lease.json || true")
                if ready.strip():
                    report["lease"] = json.loads(ready)
                    break
                time.sleep(3)
            else:
                execute(client, "/usr/bin/python3 " + remote + "/network.py rollback", True)
                raise RuntimeError("No DHCP lease; original AP restored over Ethernet")
        client.close()
        client = None
        netsh(args.ssid)
        for _ in range(30):
            try:
                if profile() == args.ssid:
                    break
            except RuntimeError:
                pass
            time.sleep(.5)
        else:
            raise RuntimeError("PC could not join the phone hotspot")
        pc_ip = wifi_address()
        network = ipaddress.IPv4Network(str(pc_ip) + "/24", strict=False)
        if str(network) != "192.168.43.0/24":
            raise RuntimeError("Phone subnet changed; refusing unverified discovery")
        report["pc_ip"] = str(pc_ip)
        address = None
        deadline = time.monotonic() + 150
        while time.monotonic() < deadline and address is None:
            if args.wired:
                candidate = str(ipaddress.IPv4Interface(report["lease"]["address"]).ip)
                address = find_board([ipaddress.IPv4Address(candidate)], pc_ip, host_key)
            else:
                address = find_board(network.hosts(), pc_ip, host_key)
            if address is None:
                print("WAITING_FOR_BOARD_DHCP", flush=True)
                time.sleep(3)
        if address is None:
            raise RuntimeError("No matching board SSH identity found; automatic AP rollback is armed")
        print("Z15_HOTSPOT_ADDRESS " + address, flush=True)
        client = connect(address)
        if client.get_transport().get_remote_server_key().asbytes() != host_key:
            raise RuntimeError("SSH identity changed")
        report["board_ip"] = address
        report["after_hashes"] = protected(client)
        report["after_services"] = execute(client, "systemctl show guardianloop-web.service guardianloop-cyton.service -p Id -p MainPID -p NRestarts -p ActiveState")
        report["link"] = execute(client, "ip -br addr; ip route; iw dev wlan0 link; resolvectl status wlan0")
        report["lease"] = json.loads(execute(client, "cat " + remote + "/lease.json"))
        report["http"] = execute(client, "curl --noproxy '*' -s -o /dev/null -w '%{http_code}' --max-time 5 http://127.0.0.1:9102/mobile")
        report["internet"] = execute(client, "curl --noproxy '*' -I --max-time 12 http://connectivitycheck.gstatic.com/generate_204 2>&1 || true")
        report["board_boot_unchanged"] = execute(client, "cat /proc/sys/kernel/random/boot_id").strip() == report["boot_id"]
        report["protected_files_unchanged"] = report["before_hashes"] == report["after_hashes"]
        response = subprocess.run(["curl.exe", "--noproxy", "*", "--max-time", "6", "-s", "-o", "NUL", "-w", "%{http_code}", "http://" + address + ":9102/mobile"], capture_output=True)
        report["pc_http"] = response.stdout.decode()
        if not report["protected_files_unchanged"] or not report["board_boot_unchanged"] or report["pc_http"] != "200":
            execute(client, "/usr/bin/python3 " + remote + "/network.py rollback", True)
            raise RuntimeError("Verification failed; original AP restoration requested")
        execute(client, "systemd-run --unit=" + identifier + "-guard /usr/bin/python3 " + remote + "/network.py guard", True)
        execute(client, "systemctl stop " + identifier + "-rollback.timer", True)
        report["confirmed"] = True
        print("HOTSPOT_LINK_AND_WEB_VERIFIED", flush=True)
    finally:
        if client is not None:
            client.close()
        netsh(original)
        report["pc_original_profile"] = original
        with (folder / "result.json").open("x", encoding="utf-8") as stream:
            json.dump(report, stream, ensure_ascii=False, indent=2)
        print("REPORT " + str(folder / "result.json"), flush=True)
        print("PC_WIFI_RESTORE_REQUESTED " + original, flush=True)


if __name__ == "__main__":
    main()

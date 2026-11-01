"""Stage a finite independent phone-eye session; no formal app, PL or COM16 writes."""
import argparse
import hashlib
import json
from pathlib import Path
import shlex
import sys
import time

from audit_z15 import board_connection, execute
from network_receiver import load_config
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "eeg_apps_z15"))
from run_ssvep_backlog_replay import checked

ROOT = Path(__file__).resolve().parent
PYTHON = "/usr/local/share/pynq-venv/bin/python3"
NATIVE = "/home/xilinx/tobii_z15/is4-calibration"
FILES = ("phone_eye_session.py", "network_receiver.py", "eye_gate.py", "network_acceptance.py", "phone_control.html")


def save(path, value):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)


def snapshot(client, paths):
    script = ("import hashlib,json,pathlib; print(json.dumps({p:hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest() "
              "for p in " + repr(list(paths)) + "}))")
    return dict(boot_id=execute(client, "cat /proc/sys/kernel/random/boot_id").strip(),
                hashes=json.loads(execute(client, PYTHON + " -c " + shlex.quote(script))),
                services=execute(client, "systemctl show guardianloop-cyton.service guardianloop-web.service "
                                 "-p MainPID -p NRestarts -p ActiveState"),
                web_service=execute(client, "systemctl show guardianloop-web.service -p MainPID -p NRestarts -p ActiveState"),
                startup_sha256=hashlib.sha256(execute(client, "systemctl cat guardianloop-cyton.service guardianloop-web.service").encode()).hexdigest())


def preflight(client, audit, config):
    observed = snapshot(client, audit["protected_sha256"])
    if observed["hashes"] != audit["protected_sha256"]:
        raise RuntimeError("Protected brain/eye files changed since preflight; deployment stopped")
    if "ActiveState=active" not in observed["web_service"]:
        raise RuntimeError("Formal webpage service is not active")
    script = """import json,pathlib,socket,subprocess
devices=[]
for p in pathlib.Path('/sys/bus/usb/devices').iterdir():
    if (p/'idVendor').exists() and (p/'idProduct').exists():
        if (p/'idVendor').read_text().strip()=='2104' and (p/'idProduct').read_text().strip()=='0124':devices.append(p.name)
processes=subprocess.check_output(['ps','-eo','comm=']).decode().splitlines()
eye=[p.strip() for p in processes if p.strip()=='is4-calibration']
s=socket.socket();s.bind(('192.168.50.1',9117));s.close()
print(json.dumps(dict(eye_usb_devices=devices,active_eye_processes=eye,port_9117_free=True,cyton_port_present=pathlib.Path('/dev/ttyUSB0').exists())))
"""
    hardware = json.loads(execute(client, PYTHON + " -c " + shlex.quote(script)))
    if len(hardware["eye_usb_devices"]) != 1 or hardware["active_eye_processes"]:
        raise RuntimeError("Eye USB missing/ambiguous or already owned; no sampler opened")
    if not hardware["cyton_port_present"]:
        hardware["cyton_prior_issue"] = execute(client, "journalctl -u guardianloop-cyton --no-pager -n 30")
        if "No such file or directory: '/dev/ttyUSB0'" not in hardware["cyton_prior_issue"]:
            raise RuntimeError("Brain acquisition health is unknown; deployment stopped")
    elif observed["services"].count("ActiveState=active") != 2:
        raise RuntimeError("Unexpected acquisition service state with its port present")
    neighbor = execute(client, "ip neigh show " + config["receiver_ip"] + " dev wlan0").lower()
    if config["receiver_mac"].lower() not in neighbor:
        execute(client, "ping -c 1 -W 1 " + config["receiver_ip"] + " >/dev/null || true")
        neighbor = execute(client, "ip neigh show " + config["receiver_ip"] + " dev wlan0").lower()
    if config["receiver_mac"].lower() not in neighbor:
        raise RuntimeError("Station IP does not map to the verified spare ESP MAC; no command sent")
    return observed, hardware


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(exist_ok=False)
    audit = json.loads((ROOT / "output/z15_wireless_eye_preflight_20261006.json").read_text(encoding="utf-8"))
    config = load_config(ROOT / "build/network_private.json")
    report = dict(phase="preflight", pl_programmed=False, formal_apps_modified=False,
                  com16_operated=False, receiver_mac=config["receiver_mac"], receiver_ip=config["receiver_ip"])
    unit = "phone-eye-wireless-" + time.strftime("%Y%m%d-%H%M%S")
    launched = False
    with board_connection() as client:
        try:
            before, hardware = preflight(client, audit, config)
            report.update(before=before, hardware=hardware, unit=unit)
            stage = execute(client, "mktemp -d /home/xilinx/phone-eye-wireless-XXXXXX").strip()
            if not stage.startswith("/home/xilinx/phone-eye-wireless-") or "/" in stage[len("/home/xilinx/"):]:
                raise ValueError("Unexpected independent stage path")
            report["stage"] = stage
            with client.open_sftp() as sftp:
                sftp.chmod(stage, 0o700)
                for name in FILES:
                    sftp.put(str(ROOT / name), stage + "/" + name)
                    sftp.chmod(stage + "/" + name, 0o600)
                sftp.put(str(ROOT / "build/network_private.json"), stage + "/network_private.json")
                sftp.chmod(stage + "/network_private.json", 0o600)
                sftp.mkdir(stage + "/tests", mode=0o700)
                for name in ("test_wireless.py", "test_phone_session.py"):
                    sftp.put(str(ROOT / "tests" / name), stage + "/tests/" + name)
            tests = execute(client, "cd " + shlex.quote(stage) + " && " + PYTHON + " -m unittest discover -s tests -v 2>&1")
            report["board_tests"] = tests
            acceptance = json.loads(execute(client, PYTHON + " " + shlex.quote(stage + "/network_acceptance.py")
                                           + " --config " + shlex.quote(stage + "/network_private.json")))
            if acceptance.get("passed") is not True or acceptance.get("hid_commands_delta") != 0:
                raise RuntimeError("Wireless virtual acceptance failed; no UI session launched")
            report["virtual_acceptance"] = acceptance
            launch = ("systemd-run --unit=" + unit + " --property=RuntimeMaxSec=1800 --property=TimeoutStopSec=15 "
                      "--property=KillMode=control-group --property=Restart=no --property=UMask=0077 "
                      "--property=WorkingDirectory=" + stage + " " + PYTHON + " -u " + stage + "/phone_eye_session.py"
                      + " --config " + stage + "/network_private.json --native " + NATIVE + " --seconds 1800")
            checked(client, launch, sudo=True)
            launched = True
            status = None
            for _ in range(20):
                try:
                    query = "import json,urllib.request; print(urllib.request.urlopen('http://192.168.50.1:9117/api/status',timeout=1).read().decode())"
                    status = json.loads(execute(client, PYTHON + " -c " + shlex.quote(query)))
                    break
                except RuntimeError:
                    time.sleep(.25)
            if not status or status["output_mode"] != "off" or status["native_ready"] or status["trained"]:
                raise RuntimeError("New session not in initial no-USB/no-output state")
            report["initial_status"] = status
            after = snapshot(client, before["hashes"])
            if any(before[key] != after[key] for key in ("boot_id", "hashes", "startup_sha256", "web_service")):
                raise RuntimeError("Protected files, services or board boot changed during deployment")
            report.update(phase="ready_for_human_calibration", after=after, protected_unchanged=True,
                          url="http://192.168.50.1:9117/", runtime_limit_seconds=1800,
                          actual_eye_control_accepted=False, actual_hid_return_validated=False)
            report["brain_acquisition_healthy"] = hardware["cyton_port_present"] and before["services"] == after["services"]
            save(args.output / "deployment.json", report)
            print(json.dumps({key: report[key] for key in ("phase", "stage", "unit", "url", "protected_unchanged", "virtual_acceptance")}, ensure_ascii=False, indent=2))
        except Exception as error:
            if launched:
                checked(client, "systemctl stop " + unit + ".service", sudo=True)
            report.update(phase="failed_session_stopped" if launched else "failed_before_launch", error_type=type(error).__name__)
            save(args.output / "failure.json", report)
            raise


if __name__ == "__main__":
    main()

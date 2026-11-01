"""Restore only this upload trial; retain uploaded media and formal runtime."""
import json
from pathlib import Path
import sys
import time

base = Path(__file__).resolve().parent
state = json.loads((base / "state.json").read_text())
sys.path.insert(0, str(Path(state["ap_helper"]).parent))
from board_control import ap_healthy, run

run(["systemctl", "stop", state["server_unit"] + ".service"], False)
if not ap_healthy():
    run(["/usr/bin/python3", str(base / "network.py"), "rollback"])
else:
    for suffix in ("guard", "wpa", "dhcp", "switch"):
        run(["systemctl", "stop", state["prefix"] + "-" + suffix + ".service"], False)
deadline = time.monotonic() + 15
healthy = ap_healthy()
while not healthy and time.monotonic() < deadline:
    time.sleep(.5)
    healthy = ap_healthy()
result = {"ap_restored": healthy, "uploaded_files_retained": True}
(base / "restore.json").write_text(json.dumps(result))
print(json.dumps(result), flush=True)
if not healthy:
    raise RuntimeError("Original AP is not ready")

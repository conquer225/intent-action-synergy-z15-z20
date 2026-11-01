"""Package the verified default delivery; never includes private WifiConfig.h."""
from pathlib import Path
from datetime import datetime
import hashlib
import json
import zipfile

ROOT = Path(__file__).resolve().parent.parent
NAME = "MultiControlS3_LAN_20261005"
BLOCKED = {"__pycache__", "build", ".git", ".pio", "Objects", "Listings", "DebugConfig"}
SUFFIXES = {".obj", ".exe", ".pdb", ".ilk", ".pyc", ".elf", ".map", ".d", ".o", ".lst", ".bak", ".uvguix.conquer"}
def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def selected():
    paths = [ROOT / p for p in ("README.md", "使用说明_新版.md", ".gitignore")]
    for folder in ("esp32/MultiControlS3", "esp01", "hand_nano", "shared", "stm32", "tests", "tools", "docs", "records", "firmware"):
        for path in (ROOT/folder).rglob("*"):
            rel=path.relative_to(ROOT)
            if path.is_file() and not any(p in BLOCKED for p in rel.parts) and path.suffix.lower() not in SUFFIXES and path.name != "WifiConfig.h":
                paths.append(path)
    return sorted(set(paths))
def main():
    for folder in ("esp32/MultiControlS3", "esp01/PendulumBridge"):
        if (ROOT/folder/"WifiConfig.h").exists():
            raise SystemExit("This package is for default builds only; a personal-config BIN may embed Wi-Fi credentials.")
    configs=[ROOT/"esp32/MultiControlS3/HandConfig.h", ROOT/"hand_nano/hand_controller/HandConfig.h"]
    assert configs[0].read_bytes()==configs[1].read_bytes()
    assert "SAFE_POSE_VERIFIED = false" in configs[0].read_text()
    protocol=[ROOT/p for p in ("shared/BridgeProtocol.h", "esp32/MultiControlS3/BridgeProtocol.h", "esp01/PendulumBridge/BridgeProtocol.h")]
    assert len({p.read_bytes() for p in protocol})==1
    paths=selected()
    manifest={
      "project":"MultiControlS3 LAN + five-finger feedback", "delivery_date":"2026-10-05",
      "wiring":{"emg_signal":1,"emg_wear":2,"mpu_sda":11,"mpu_scl":12,"pots":[4,5,6,7,9,10],"rf_ce":42,"rf_csn":41,"rf_sck":40,"rf_mosi":39,"rf_miso":38,"motors":[15,16,17,18,8],"nano_pressure":["A0","A1","A2","A3","A4"],"stm_uart_tx":"PA9","stm_uart_rx":"PA10"},
      "interfaces":{"tcp":9000,"udp":9001,"stm_baud":9600,"rf_control_bytes":14,"rf_feedback_bytes":13},
      "builds":{"esp32":{"core":"3.3.11","program":982280,"static_ram":57976,"result":"PASS"},"esp01":{"core":"3.1.2","flash_code":243568,"ram":28340,"result":"PASS"},"nano":{"core":"1.8.6","program":5518,"ram":509,"result":"PASS"},"stm32":{"compiler":"ARMCC 5.06u5","errors":0,"warnings":0,"source_changed_this_round":False,"result":"PASS"}},
      "default_config":{"wifi_configured":False,"hand_safe_pose_verified":False,"motion_enabled_at_boot":False},
      "verification":{"bridge_and_stm_host":"PASS","s3_actual_sketch_fake_hardware":"PASS","nano_actual_sketch_fake_hardware":"PASS","production_json_parser":"PASS","pc_localhost_tests":15,"gui_hidden_construction":"PASS","hardware_uploaded":False,"hardware_chain_validated":False},
      "original_projects_modified":False,
      "sha256":{str(p.relative_to(ROOT)).replace("\\","/"):digest(p) for p in paths}
    }
    manifest_path=ROOT/"交付清单.json"
    manifest_path.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    archive=ROOT/(NAME+".zip")
    with zipfile.ZipFile(archive,"w",zipfile.ZIP_DEFLATED) as z:
        for p in paths+[manifest_path]:z.write(p,NAME+"/"+str(p.relative_to(ROOT)).replace("\\","/"))
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        for rel,expected in manifest["sha256"].items():
            assert hashlib.sha256(z.read(NAME+"/"+rel)).hexdigest()==expected,rel
        assert not any("WifiConfig.h" in p or "/build/" in p or "__pycache__" in p for p in z.namelist())
    checksum=digest(archive)
    (ROOT/(NAME+".sha256.txt")).write_text(checksum+"  "+archive.name+"\n",encoding="utf-8")
    print(json.dumps({"archive":str(archive),"files":len(paths)+1,"bytes":archive.stat().st_size,"sha256":checksum},ensure_ascii=False))
if __name__=="__main__":main()

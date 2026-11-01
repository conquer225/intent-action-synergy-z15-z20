"""An update package for the already-working Tobii board install, with real media."""
import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def package():
    from prepare_media import verify
    verify(ROOT / "media")
    files = [(p, "src/"+p.name) for p in sorted((ROOT / "src").glob("*.py"))]
    files += [(p, "media/"+p.relative_to(ROOT / "media").as_posix())
              for p in sorted((ROOT / "media").rglob("*")) if p.is_file()]
    files += [(ROOT / "tools/start_local_media.sh", "start_local_media.sh"),
              (ROOT / "tools/display_session.sh", "display_session.sh"),
              (ROOT / "tools/check_local_media_board.py", "tools/check_local_media_board.py"),
              (ROOT / "tools/setup_usb_audio.sh", "tools/setup_usb_audio.sh"),
              (ROOT / "tools/build_usb_audio.sh", "tools/build_usb_audio.sh"),
              (ROOT / "LOCAL_MEDIA.md", "LOCAL_MEDIA.md")]
    files += [(p,"bin/"+p.name) for p in sorted((ROOT/"bin").iterdir()) if p.is_file()]
    files += [(p,"drivers/"+p.relative_to(ROOT/"drivers").as_posix())
              for p in sorted((ROOT/"drivers").rglob("*")) if p.is_file()]
    files += [(ROOT/"tests"/name,"tests/"+name)
              for name in ("test_media.py","test_recalibration.py",
                           "test_distance_display.py","test_tracking.py")]
    for name in ("local_media_verification.md","local_media_tests_final_1005.txt",
                 "local_media_arm_tests_final_1005.txt","local_media_contact_1005.jpg",
                 "local_media_hdmi_final_1005.txt","usb_audio_driver_1005.txt",
                 "recalibration_1005.md","recalibration_tests_1005.txt",
                 "recalibration_arm_tests_1005.txt","recalibration_board_ready_1005.txt",
                 "distance_display_1005.md","distance_display_tests_1005.txt",
                 "distance_display_arm_tests_1005.txt","distance_display_contact_1005.jpg",
                 "distance_display_board_1005.txt","recalibration_accuracy_summary_1005.txt",
                 "recalibration_position_result_1005.txt","distance_display_render_timing_1005.txt"):
        files.append((ROOT/"report"/name,"report/"+name))
    target = ROOT / "build/Z15_Local_Media_20261005.zip"
    target.parent.mkdir(exist_ok=True)
    hashes = {name: hashlib.sha256(path.read_bytes()).hexdigest() for path, name in files}
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path, name in files:
            if name == "bin/aplay":
                entry=zipfile.ZipInfo(name)
                entry.create_system=3
                entry.external_attr=(0o100755 << 16)
                entry.compress_type=zipfile.ZIP_DEFLATED
                archive.writestr(entry,path.read_bytes())
            else:
                archive.write(path, name)
        archive.writestr("update_hashes.json", json.dumps(hashes, indent=2)+"\n")
    with zipfile.ZipFile(target) as archive:
        if archive.testzip() is not None:
            raise RuntimeError("Invalid package")
        for name, expected in hashes.items():
            if hashlib.sha256(archive.read(name)).hexdigest() != expected:
                raise RuntimeError("Package content mismatch: " + name)
    print(json.dumps(dict(path=str(target), files=len(files),
                         bytes=target.stat().st_size), ensure_ascii=False))
    return target


if __name__ == "__main__":
    package()

"""PC-only: turn the reference project's real assets into offline SD materials."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import wave

PHRASES = ("我需要喝水", "我需要吃东西", "我需要上厕所",
           "请帮我调整姿势", "是的", "不是")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare(reference, output, ffmpeg):
    reference, output = reference.resolve(), output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    for name in ("speech", "music", "videos"):
        (output / name).mkdir(exist_ok=True)
    # Use the existing working reference voice on the PC, never on ARM.
    sys.path.insert(0, str(reference))
    from speech import Speaker
    speaker = Speaker(reference / "voice")
    manifest = dict(version=1, audio_device="default", speech=[], music=[], videos=[])
    provenance = dict(reference=str(reference), voice_model="zh_CN-xiao_ya-medium.onnx",
                      voice_model_sha256=digest(reference / "voice/zh_CN-xiao_ya-medium.onnx"),
                      voice_license=(reference / "voice/MODEL_CARD").read_text(encoding="utf-8"),
                      music=[], videos=[])
    for index, phrase in enumerate(PHRASES, 1):
        path = output / "speech" / ("%02d.wav" % index)
        path.write_bytes(speaker.synthesize(phrase))
        manifest["speech"].append(dict(label=phrase, path=path.relative_to(output).as_posix()))
        print("speech", index, phrase, path.stat().st_size, flush=True)
    songs = json.loads((reference / "music/playlist.json").read_text(encoding="utf-8"))
    for index, row in enumerate(songs["tracks"][:3], 1):
        source = reference / "music" / row["file"]
        path = output / "music" / ("%02d.wav" % index)
        subprocess.run([str(ffmpeg), "-hide_banner", "-loglevel", "error", "-y",
                        "-i", str(source), "-vn", "-acodec", "pcm_s16le",
                        "-ar", "44100", "-ac", "2", str(path)], check=True)
        manifest["music"].append(dict(label=row["title"], path=path.relative_to(output).as_posix()))
        provenance["music"].append(dict(**row, source=songs["source"],
            license=songs["license"], source_sha256=digest(source)))
        print("music", index, path.stat().st_size, flush=True)
    clips = json.loads((reference / "videos/playlist.json").read_text(encoding="utf-8"))
    for index, row in enumerate(clips[:2], 1):
        source = reference / "videos" / row["file"]
        folder = output / "videos" / ("%02d" % index)
        folder.mkdir(exist_ok=True)
        for existing in folder.glob("frame_*.jpg"):
            if existing.resolve().parent != folder.resolve():
                raise ValueError("Unexpected frame target")
            existing.unlink()
        subprocess.run([str(ffmpeg), "-hide_banner", "-loglevel", "error", "-y",
                        "-i", str(source), "-an", "-vf",
                        "fps=10,scale=640:360:force_original_aspect_ratio=decrease,pad=640:360:(ow-iw)/2:(oh-ih)/2",
                        "-q:v", "4", str(folder / "frame_%06d.jpg")], check=True)
        count = len(list(folder.glob("frame_*.jpg")))
        if not count:
            raise ValueError("No frames extracted")
        manifest["videos"].append(dict(label=("小奶猫", "小狗")[index-1],
            path=folder.relative_to(output).as_posix(), fps=10, frames=count))
        provenance["videos"].append(dict(**row, source_sha256=digest(source)))
        print("video", index, count, "frames", flush=True)
    for name, data in (("playlist.json", manifest), ("provenance.json", provenance)):
        (output / name).write_text(json.dumps(data, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    hashes = {p.relative_to(output).as_posix(): digest(p)
              for p in sorted(output.rglob("*")) if p.is_file() and p.name != "hashes.json"}
    (output / "hashes.json").write_text(json.dumps(hashes, indent=2)+"\n", encoding="utf-8")
    return verify(output)


def verify(output):
    from PIL import Image
    output = output.resolve()
    manifest = json.loads((output / "playlist.json").read_text(encoding="utf-8"))
    hashes = json.loads((output / "hashes.json").read_text(encoding="utf-8"))
    for relative, expected in hashes.items():
        path = (output / relative).resolve()
        if output not in path.parents or digest(path) != expected:
            raise ValueError("Asset hash mismatch: " + relative)
    seconds = {}
    for group in ("speech", "music"):
        for row in manifest[group]:
            with wave.open(str(output / row["path"]), "rb") as audio:
                if audio.getsampwidth() != 2 or audio.getcomptype() != "NONE" or not audio.getnframes():
                    raise ValueError("Invalid PCM WAV: " + row["path"])
                seconds[row["path"]] = round(audio.getnframes()/audio.getframerate(), 3)
    for row in manifest["videos"]:
        for index in range(1, row["frames"] + 1):
            with Image.open(output / row["path"] / ("frame_%06d.jpg" % index)) as picture:
                if picture.size != (640, 360):
                    raise ValueError("Incorrect frame size")
                picture.verify()
        seconds[row["path"]] = row["frames"]/row["fps"]
    report = dict(files=len(hashes), bytes=sum((output / p).stat().st_size for p in hashes),
                  speech=len(manifest["speech"]), music=len(manifest["music"]),
                  videos=len(manifest["videos"]), durations_seconds=seconds)
    print(json.dumps(report, ensure_ascii=False), flush=True)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--reference", type=Path)
    parser.add_argument("--ffmpeg", type=Path)
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parents[1]/"media")
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    if args.verify:
        verify(args.output)
    else:
        if not args.reference or not args.ffmpeg:
            parser.error("--reference and --ffmpeg are required for preparation")
        prepare(args.reference, args.output, args.ffmpeg)

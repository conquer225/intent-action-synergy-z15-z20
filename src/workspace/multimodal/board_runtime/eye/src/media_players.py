"""Offline players. Audio has one child; video has one bounded latest-frame slot."""
from dataclasses import dataclass
from pathlib import Path
import math
import queue
import shutil
import subprocess
import threading
import time
from PIL import Image


@dataclass(frozen=True)
class Asset:
    label: str
    path: Path
    frames: int = 0
    fps: float = 10.0


class AudioPlayer:
    def __init__(self, device="default", executable=None):
        self.device = device
        bundled = Path(__file__).resolve().parents[1] / "bin/aplay"
        self.executable = executable or shutil.which("aplay") or (str(bundled) if bundled.is_file() else None)
        self.process = None
        self.reader = None
        self.errors = bytearray()
        self.status = "idle"
        self.error = ""

    def stop(self):
        process, self.process = self.process, None
        if process is not None:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=.35)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=.35)
            if self.reader is not None:
                self.reader.join(timeout=.2)
            process.stderr.close()
        self.reader = None
        self.status = "idle"

    @staticmethod
    def _drain(stream, errors):
        try:
            while True:
                chunk = stream.read(512)
                if not chunk:
                    return
                errors.extend(chunk)
                if len(errors) > 4096:
                    del errors[:-4096]
        except (OSError, ValueError):
            return

    def start(self, path):
        self.stop()
        self.error = ""
        path = Path(path)
        if not path.is_file():
            self.error = "音频文件缺失：" + path.name
        elif not self.executable:
            self.error = "未找到 aplay，请安装 alsa-utils 并连接音频设备"
        if self.error:
            self.status = "error"
            return False
        self.errors = bytearray()
        try:
            self.process = subprocess.Popen(
                [str(self.executable), "-q", "-D", self.device, str(path)],
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE)
        except OSError as exc:
            self.error = "音频播放器无法启动：" + str(exc)
            self.status = "error"
            return False
        self.reader = threading.Thread(
            target=self._drain, args=(self.process.stderr, self.errors), daemon=True)
        self.reader.start()
        self.status = "playing"
        return True

    def poll(self):
        """Return a completion once. Process success is not measured audibility."""
        if self.process is None or self.process.poll() is None:
            return None
        code = self.process.returncode
        self.reader.join(timeout=.2)
        detail = self.errors.decode("utf-8", "replace").strip()
        self.stop()
        self.status = "complete" if code == 0 else "error"
        self.error = "" if code == 0 else "播放失败，请检查音频设备：" + (detail[-200:] or str(code))
        return self.status, self.error

    close = stop


class VideoPlayer:
    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.thread = None
        self.cancel = threading.Event()
        self.latest = queue.Queue(maxsize=1)
        self.status = "idle"
        self.error = ""
        self.generation = 0

    def stop(self):
        self.cancel.set()
        self.generation += 1
        if self.thread is not None:
            self.thread.join(timeout=.3)
        self.status = "idle"
        while not self.latest.empty():
            try:
                self.latest.get_nowait()
            except queue.Empty:
                break

    def start(self, asset):
        self.stop()
        self.error = ""
        if self.thread is not None and self.thread.is_alive():
            self.error = "上一段视频仍在关闭，请稍后重试"
        elif not asset.path.is_dir() or not (asset.path / "frame_000001.jpg").is_file():
            self.error = "视频素材缺失：" + asset.path.name
        elif (type(asset.frames) is not int or not 1 <= asset.frames <= 36000 or
              not math.isfinite(asset.fps) or not 1 <= asset.fps <= 30):
            self.error = "视频帧数或速度配置无效"
        if self.error:
            self.status = "error"
            return False
        self.cancel = threading.Event()
        self.status = "playing"
        self.thread = threading.Thread(
            target=self._run, args=(asset, self.generation, self.cancel), daemon=True)
        self.thread.start()
        return True

    def _run(self, asset, generation, cancel):
        started, previous = self.clock(), -1
        try:
            while not cancel.is_set():
                elapsed = max(0., self.clock() - started)
                index = int(elapsed * asset.fps)
                if index >= asset.frames:
                    if generation == self.generation:
                        self.status = "complete"
                    return
                if index != previous:
                    with Image.open(asset.path / ("frame_%06d.jpg" % (index + 1))) as source:
                        if source.size != (640, 360):
                            raise ValueError("视频帧必须为 640×360")
                        picture = source.convert("RGB")
                    if cancel.is_set() or generation != self.generation:
                        return
                    try:
                        self.latest.get_nowait()
                    except queue.Empty:
                        pass
                    self.latest.put_nowait((index, picture))
                    previous = index
                due = started + (index + 1) / asset.fps - self.clock()
                cancel.wait(max(.001, min(.1, due)))
        except Exception as exc:
            if generation == self.generation:
                self.error = "视频播放失败：" + str(exc)
                self.status = "error"

    def poll(self):
        try:
            frame = self.latest.get_nowait()
        except queue.Empty:
            frame = None
        return frame, self.status, self.error

    close = stop

"""Three-region menus sharing the verified Selection object, not a second dwell."""
from dataclasses import dataclass, field
import json
from pathlib import Path
import time
from guide import View
from selection import Selection
from media_players import Asset, AudioPlayer, VideoPlayer

READ_SECONDS = 1.2
GROUPS = ("speech", "videos", "music")
TITLES = {"home": "请选择功能", "speech": "句子发声",
          "videos": "选择视频", "music": "选择音乐", "music_player": "音乐播放"}


class Catalog:
    def __init__(self, directory):
        self.root = Path(directory).resolve()
        self.groups = {key: [] for key in GROUPS}
        self.device = "default"
        self.error = ""
        try:
            data = json.loads((self.root / "playlist.json").read_text(encoding="utf-8"))
            if data.get("version") != 1:
                raise ValueError("素材列表版本不支持")
            self.device = str(data.get("audio_device", "default"))
            for group in GROUPS:
                for row in data.get(group, []):
                    relative = Path(row["path"])
                    path = (self.root / relative).resolve()
                    if relative.is_absolute() or self.root not in path.parents:
                        raise ValueError("素材路径必须位于 media 目录内")
                    self.groups[group].append(Asset(str(row["label"]), path,
                        int(row.get("frames", 0)), float(row.get("fps", 10))))
        except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
            self.groups = {key: [] for key in GROUPS}
            self.error = "素材列表无法读取：" + str(exc)


@dataclass(frozen=True)
class MenuView(View):
    title: str = ""
    labels: tuple = ()
    subtitle: str = ""
    footer: str = ""
    page_id: int = 0
    reading: bool = False
    video_frame: int = -1
    video_image: object = field(default=None, compare=False, repr=False)


class MediaMenu:
    def __init__(self, catalog, selection=None, audio=None, video=None,
                 now=None, audio_device=None):
        self.catalog = catalog
        self.selection = selection or Selection()
        self.audio = audio or AudioPlayer(audio_device or catalog.device)
        self.video = video or VideoPlayer()
        self.page = "home"
        self.offset = 0
        self.song = 0
        self.page_id = 0
        self.presented_page = -1
        self.read_until = (time.monotonic() if now is None else now) + READ_SECONDS
        self.detail = catalog.error or "选择句子、视频或音乐"
        self.picture = None
        self.frame = -1
        self.video_offset = 0
        self.last_action = ""

    def presented(self, now):
        """Start reading only after this page's flushed HDMI buffer is parked."""
        if self.presented_page != self.page_id:
            self.presented_page = self.page_id
            self.read_until = now + READ_SECONDS
            self.selection.clear_pending()

    def _enter(self, page, now, offset=0):
        self.audio.stop()
        self.video.stop()
        self.page, self.offset = page, offset
        self.page_id += 1
        self.read_until = now + READ_SECONDS
        self.selection.clear_pending()  # preserves locked and confirmed count
        self.picture, self.frame = None, -1
        self.detail = self.catalog.error or ""

    def gaze(self, event, now):
        stamp = event.get("monotonic_ns")
        if (self.page == "video" or self.selection.paused or now < self.read_until or
            self.presented_page != self.page_id or type(stamp) is not int or
            stamp / 1e9 < self.read_until):
            self.selection.clear_pending()
            return False
        if self.selection.update_horizontal(event, now):
            self.choose(self.selection.selected, now)
            return True
        return False

    def choose(self, region, now):
        if (type(region) is not int or not 0 <= region < 3 or
            self.page == "video" or self.selection.paused or now < self.read_until):
            return
        self.last_action = self.page + ":" + str(region)
        if self.page == "home":
            self._enter(GROUPS[region], now)
        elif self.page in GROUPS:
            entries = self.catalog.groups[self.page]
            if region == 2:
                if self.offset + 2 < len(entries):
                    self._enter(self.page, now, self.offset + 2)
                else:
                    self._enter("home", now)
                return
            index = self.offset + region
            if index >= len(entries):
                return
            asset = entries[index]
            if self.page == "speech":
                self.detail = ("正在发声：" + asset.label if self.audio.start(asset.path)
                               else self.audio.error)
            elif self.page == "music":
                self.song = index
                self._enter("music_player", now)
                self._play_song()
            else:
                self.video_offset = self.offset
                self._enter("video", now)
                self.detail = asset.label
                if not self.video.start(asset):
                    error = self.video.error
                    self._enter("videos", now, self.video_offset)
                    self.detail = error
        elif self.page == "music_player":
            if region == 0:
                if self.audio.status == "playing":
                    self.audio.stop()
                    self.detail = "已停止，选择左区可从头播放"
                else:
                    self._play_song()
            elif region == 1:
                self.song = (self.song + 1) % len(self.catalog.groups["music"])
                self._enter("music_player", now)
                self._play_song()
            else:
                self._enter("music", now, self.song // 2 * 2)

    def _play_song(self):
        asset = self.catalog.groups["music"][self.song]
        self.detail = ("正在播放：" + asset.label if self.audio.start(asset.path)
                       else self.audio.error)

    def pause(self, now):
        if self.page == "video":
            self._enter("videos", now, self.video_offset)
            self.detail = "视频已退出"
            return
        self.selection.toggle_pause()
        self.audio.stop()
        self.page_id += 1
        self.read_until = now + READ_SECONDS
        self.detail = "已暂停，按 PS_KEY1 继续" if self.selection.paused else "已继续，请重新选择"

    def tick(self, now):
        result = self.audio.poll()
        if result is not None:
            status, error = result
            self.detail = error or ("发声播放结束" if self.page == "speech"
                                   else "歌曲播放结束，等待下一次选择")
        if self.page == "video":
            frame, status, error = self.video.poll()
            if frame is not None:
                self.frame, self.picture = frame
            if status in ("complete", "error"):
                self._enter("videos", now, self.video_offset)
                self.detail = error or "视频播放结束"

    def view(self, now):
        selected = self.selection.view(now)
        reading = now < self.read_until or self.presented_page != self.page_id
        if self.page == "video":
            return MenuView(phase="video", title="正在观看", subtitle=self.detail,
                footer="无声视频 · PS_KEY0 重新标定 · PS_KEY1 退出",
                page_id=self.page_id, video_frame=self.frame, video_image=self.picture)
        if self.page == "home":
            labels, subtitle = ("句子发声", "看视频", "听音乐"), "固定发声 · 无声视频 · 本地音乐"
        elif self.page == "music_player":
            labels = ("停止" if self.audio.status == "playing" else "从头播放",
                      "下一首", "返回列表")
            subtitle = self.catalog.groups["music"][self.song].label
        else:
            entries = self.catalog.groups[self.page]
            labels = tuple(a.label for a in entries[self.offset:self.offset + 2])
            labels += ("",) * (2 - len(labels))
            labels += ("下一页" if self.offset + 2 < len(entries) else "返回主页",)
            subtitle = ("第 %d / %d 页" % (self.offset // 2 + 1, max(1, (len(entries) + 1) // 2))
                        if entries else "暂无素材，选择右区返回")
        return MenuView(phase="menu", title=TITLES[self.page], labels=labels,
            subtitle=subtitle, detail=self.detail, page_id=self.page_id,
            hover=selected.hover if not reading else -1,
            selected=selected.selected, progress=selected.progress if not reading else 0,
            confirmations=selected.confirmations, paused=selected.paused, reading=reading,
            footer="已暂停 · PS_KEY0 重新标定 · PS_KEY1 继续" if selected.paused else
                   "请先阅读，稍后选择" if reading else
                   "停留约 1.4 秒 · 换区后再次选择 · PS_KEY0 重新标定 · PS_KEY1 暂停")

    def close(self):
        self.audio.close()
        self.video.close()

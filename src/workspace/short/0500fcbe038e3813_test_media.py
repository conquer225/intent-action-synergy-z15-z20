"""Behavioral checks with explicit fake audio; real JPEG decoding is tested separately."""
import io
import json
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
from dataclasses import replace
from PIL import Image
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from media_menu import Catalog, MediaMenu
from media_players import Asset, AudioPlayer, VideoPlayer
from guide_render import Renderer


class FakeAudio:
    def __init__(self):
        self.status, self.error = "idle", ""
        self.starts = []
        self.result = None
        self.fail = False

    def start(self, path):
        self.starts.append(path)
        self.status = "error" if self.fail else "playing"
        self.error = "音频播放失败：未接音频设备" if self.fail else ""
        return not self.fail

    def stop(self):
        self.status = "idle"

    def poll(self):
        result, self.result = self.result, None
        if result:self.status = result[0]
        return result

    close = stop


class FakeVideo:
    def __init__(self):
        self.status, self.error = "idle", ""
        self.polls = 0

    def start(self, asset):
        self.status = "playing"
        return True

    def stop(self):
        self.status = "idle"

    def poll(self):
        self.polls += 1
        return None, self.status, self.error

    close = stop


class MenuTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        data = dict(version=1, speech=[dict(label="短句%d"%i,path="speech/%d.wav"%i) for i in range(6)],
                    music=[dict(label="歌曲%d"%i,path="music/%d.wav"%i) for i in range(3)],
                    videos=[dict(label="视频",path="videos/01",fps=10,frames=3)])
        (root/"playlist.json").write_text(json.dumps(data),encoding="utf-8")
        self.audio, self.video = FakeAudio(), FakeVideo()
        self.menu = MediaMenu(Catalog(root),audio=self.audio,video=self.video,now=10)
        self.menu.presented(10)
        self.addCleanup(self.menu.close)
        self.addCleanup(self.temp.cleanup)

    def hold(self, start, x, seconds):
        count = 0
        for i in range(round(seconds*60)):
            now = start+i/60
            event = dict(valid=True,x=x,monotonic_ns=round(now*1e9))
            count += self.menu.gaze(event,now)
            self.menu.tick(now)
            self.menu.presented(now)
        return count

    def click(self, region, now):
        self.menu.choose(region,now)
        self.menu.presented(now)

    def test_page_read_and_original_region_lock_prevent_chain_speech(self):
        self.assertEqual(self.hold(11.3,.2,2),1)
        self.assertEqual(self.menu.page,"speech")
        self.assertEqual(self.hold(13.4,.2,5),0)
        self.assertEqual(len(self.audio.starts),0)
        self.hold(18.5,.5,.35)  # release without dwelling long enough to select
        self.assertEqual(self.hold(18.9,.2,2),1)
        self.assertEqual(len(self.audio.starts),1)
        self.assertEqual(self.hold(21,.2,5),0)
        self.audio.result = ("complete","")
        self.menu.tick(27)
        self.assertEqual(self.menu.page,"speech")
        self.assertIn("结束",self.menu.detail)

    def test_reading_begins_at_actual_presentation_not_navigation(self):
        self.menu.presented_page = -1
        self.menu.presented(20)
        self.assertFalse(self.menu.gaze(dict(valid=True,x=.2,monotonic_ns=20_900_000_000),21.3))
        self.assertEqual(self.menu.selection.confirmations,0)
        self.assertEqual(self.hold(21.3,.2,2),1)

    def test_pagination_and_blank_slot_back(self):
        self.click(0,11.3)
        self.assertEqual(self.menu.view(13).labels[:2],("短句0","短句1"))
        self.click(2,13)
        self.click(2,15)
        self.assertEqual(self.menu.view(17).labels,("短句4","短句5","返回主页"))
        self.click(2,17)
        self.assertEqual(self.menu.page,"home")
        self.click(2,19)
        self.click(2,21)
        self.assertEqual(self.menu.view(23).labels,("歌曲2","","返回主页"))
        self.click(1,23)
        self.assertEqual(self.audio.starts,[])
        self.click(2,23)
        self.assertEqual(self.menu.page,"home")

    def test_music_restart_next_end_back_and_pause(self):
        self.click(2,11.3)
        self.click(0,13)
        self.assertEqual(self.menu.page,"music_player")
        self.assertEqual(self.audio.status,"playing")
        self.click(0,15)
        self.assertEqual(self.audio.status,"idle")
        self.click(0,17)
        self.assertEqual(len(self.audio.starts),2)
        self.click(1,19)
        self.assertEqual(self.menu.song,1)
        self.audio.result = ("complete","")
        self.menu.tick(21)
        self.assertEqual(self.menu.view(21).labels[0],"从头播放")
        self.menu.pause(22)
        self.menu.presented(22)
        self.assertTrue(self.menu.selection.paused)
        self.menu.pause(24)
        self.menu.presented(24)
        self.assertEqual(self.audio.status,"idle")
        self.click(2,26)
        self.assertEqual(self.menu.page,"music")
        self.assertEqual(self.audio.status,"idle")

    def test_video_suppresses_gaze_and_both_eof_and_button_return(self):
        self.click(1,11.3)
        self.click(0,13)
        self.assertEqual(self.menu.page,"video")
        for x in (.2,.5,.8):
            self.assertEqual(self.hold(15+x*10,x,2),0)
        self.assertGreater(self.video.polls,0)
        self.menu.pause(30)
        self.menu.presented(30)
        self.assertEqual(self.menu.page,"videos")
        self.assertFalse(self.menu.selection.paused)
        self.click(0,32)
        self.video.status = "complete"
        self.menu.tick(34)
        self.assertEqual(self.menu.page,"videos")
        self.assertIn("结束",self.menu.detail)

    def test_player_failure_does_not_claim_success_or_leave_dead_end(self):
        self.audio.fail = True
        self.click(0,11.3)
        self.click(0,13)
        self.assertIn("失败",self.menu.detail)
        self.assertEqual(self.menu.page,"speech")
        self.click(2,15)
        self.assertEqual(self.menu.offset,2)
        self.click(2,17)
        self.click(2,19)
        self.assertEqual(self.menu.page,"home")

    def test_missing_manifest_leaves_home_and_return_available(self):
        (Path(self.temp.name)/"playlist.json").unlink()
        menu = MediaMenu(Catalog(self.temp.name),audio=FakeAudio(),video=FakeVideo(),now=10)
        menu.presented(10)
        self.assertIn("无法读取",menu.view(12).detail)
        menu.choose(1,12)
        menu.presented(12)
        self.assertEqual(menu.view(14).labels,("","","返回主页"))
        menu.choose(2,14)
        self.assertEqual(menu.page,"home")
        menu.close()

    def test_invalid_and_stale_gaze_never_dispatch(self):
        for i in range(100):
            now=12+i/60
            self.menu.gaze(dict(valid=False,x=.2,monotonic_ns=round(now*1e9)),now)
        self.menu.gaze(dict(valid=True,x=.2,monotonic_ns=12_000_000_000),15)
        self.assertEqual(self.menu.page,"home")
        self.assertEqual(self.menu.selection.confirmations,0)

    def test_renderer_progress_cache_is_immutable_and_video_is_bgr(self):
        renderer=Renderer(local_media=True)
        view=replace(self.menu.view(12),hover=0,progress=0,reading=False)
        before=renderer.render(view)
        after=renderer.render(replace(view,progress=.8))
        self.assertEqual(before.shape,(720,1280,3))
        self.assertFalse((before==after).all())
        again=renderer.render(view)
        self.assertTrue((before==again).all())
        self.click(1,12)
        self.click(0,14)
        self.menu.picture=Image.new("RGB",(640,360),(255,0,0))
        self.menu.frame=0
        frame=renderer.render(self.menu.view(16))
        self.assertEqual(tuple(frame[300,400]),(0,0,255))
        shell=renderer.video_shell.copy()
        self.menu.picture=Image.new("RGB",(640,360),(0,255,0))
        self.menu.frame=1
        next_frame=renderer.render(self.menu.view(16.1))
        self.assertEqual(tuple(next_frame[300,400]),(0,255,0))
        self.assertEqual(tuple(frame[300,400]),(0,0,255))
        self.assertTrue((renderer.video_shell==shell).all())

    def test_direct_framebuffer_is_pixel_exact_across_layout_and_menu_changes(self):
        from media_menu import MenuView
        direct, reference = Renderer(local_media=True), Renderer(local_media=True)
        buffers = [np.zeros((720,1280,3), dtype=np.uint8) for _ in range(3)]
        picture = Image.fromarray(np.random.RandomState(23).randint(0,256,(360,640,3),dtype=np.uint8))
        video = MenuView(phase='video', title='正在观看', footer='无声视频', video_image=picture)
        views = [video] * 6 + [replace(video, tracking=('距离 42 cm',)),
                 replace(video, tracking=('距离 43 cm',)), video,
                 replace(video, title='新视频', page_id=2), replace(video, video_image=None),
                 MenuView(phase='menu', title='主页', labels=('句子','视频','音乐'))] + [video] * 3
        for serial, view in enumerate(views):
            buffer = buffers[serial % 3]
            self.assertIs(direct.render_into(buffer, view), buffer)
            np.testing.assert_array_equal(buffer, reference.render(view))

    def test_direct_framebuffer_reuses_shell_but_rejects_wrong_storage(self):
        from media_menu import MenuView
        renderer = Renderer(local_media=True)
        video = MenuView(phase='video', title='视频', video_image=Image.new('RGB',(640,360),'red'))
        buffer = np.zeros((720,1280,3), dtype=np.uint8)
        renderer.render_into(buffer, video)
        with patch('guide_render.np.copyto', wraps=np.copyto) as copyto:
            renderer.render_into(buffer, video)
            copyto.assert_not_called()
        with self.assertRaises(ValueError):renderer.render_into(buffer.astype(np.float32),video)
        with self.assertRaises(ValueError):renderer.render_into(buffer[:100],video)


class PlayerTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)

    def clip(self,count=8,size=(640,360)):
        for index in range(1,count+1):
            Image.new("RGB",size,(index,20,30)).save(self.root/("frame_%06d.jpg"%index))
        return Asset("clip",self.root,count,10)

    def test_real_decoder_latest_slot_and_eof_use_wall_time(self):
        video=VideoPlayer()
        self.addCleanup(video.close)
        asset=self.clip()
        started=time.monotonic()
        self.assertTrue(video.start(asset))
        time.sleep(.28)
        frame,status,error=video.poll()
        self.assertGreaterEqual(frame[0],1)
        self.assertEqual(frame[1].size,(640,360))
        self.assertLessEqual(video.latest.qsize(),1)
        self.assertEqual(status,"playing")
        limit=started+2
        while video.status=="playing" and time.monotonic()<limit:
            time.sleep(.01)
        self.assertEqual(video.status,"complete")
        self.assertGreaterEqual(time.monotonic()-started,.79)
        self.assertLess(time.monotonic()-started,1.5)

    def test_cancel_discards_old_frames_before_restart(self):
        video=VideoPlayer()
        self.addCleanup(video.close)
        asset=self.clip(20)
        video.start(asset)
        time.sleep(.12)
        video.stop()
        self.assertEqual(video.latest.qsize(),0)
        self.assertFalse(video.thread.is_alive())
        video.clock=lambda:10.0  # Hold frame zero; scheduling speed is not the contract.
        self.assertTrue(video.start(asset))
        frame=None
        limit=time.monotonic()+1
        while frame is None and time.monotonic()<limit:
            frame,status,error=video.poll()
            time.sleep(.01)
        self.assertIsNotNone(frame)
        self.assertEqual(frame[0],0)

    def test_missing_and_corrupt_frames_report_failure(self):
        video=VideoPlayer()
        self.addCleanup(video.close)
        self.assertFalse(video.start(Asset("missing",self.root,10)))
        asset=self.clip(2,(32,32))
        self.assertTrue(video.start(asset))
        limit=time.monotonic()+1
        while video.status=="playing" and time.monotonic()<limit:time.sleep(.01)
        self.assertEqual(video.status,"error")
        self.assertIn("640",video.error)

    def test_audio_missing_executable_and_bad_child_exit(self):
        path=self.root/"voice.wav"
        path.write_bytes(b"fixture")
        audio=AudioPlayer(executable="z15_missing_aplay_executable")
        self.assertFalse(audio.start(path))
        self.assertEqual(audio.status,"error")
        audio=AudioPlayer(executable=sys.executable)
        self.addCleanup(audio.close)
        self.assertTrue(audio.start(path))  # python rejects aplay's arguments
        result=None
        limit=time.monotonic()+2
        while result is None and time.monotonic()<limit:
            result=audio.poll()
            time.sleep(.01)
        self.assertEqual(result[0],"error")
        self.assertIn("失败",result[1])
        self.assertIsNone(audio.poll())

    def test_audio_stops_old_process_before_starting_next(self):
        log=[]
        class Child:
            def __init__(self,*args,**kwargs):
                self.stderr=io.BytesIO()
                self.returncode=None
                log.append("start")
            def poll(self):return self.returncode
            def terminate(self):log.append("terminate")
            def wait(self,timeout=None):
                self.returncode=0
                log.append("wait")
            def kill(self):log.append("kill")
        path=self.root/"voice.wav"
        path.write_bytes(b"fixture")
        with patch("media_players.subprocess.Popen",Child):
            audio=AudioPlayer(executable="fake_aplay")
            audio.start(path)
            audio.start(path)
            self.assertEqual(log[:4],["start","terminate","wait","start"])
            audio.close()


if __name__=="__main__":unittest.main()

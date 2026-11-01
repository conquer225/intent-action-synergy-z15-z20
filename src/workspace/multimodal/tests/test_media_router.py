import json,tempfile,unittest
from pathlib import Path
from intent_one.media import MediaRouter
class Audio:
    status='idle';error=''
    def __init__(self):self.starts=[]
    def start(self,path):self.starts.append(Path(path).name);self.status='playing';return True
    def stop(self):self.status='idle'
    close=stop
    def poll(self):return None
class Video:
    def __init__(self):self.starts=[];self.status='idle'
    def start(self,asset):self.starts.append(asset.path.name);self.status='playing';return True
    def stop(self):self.status='idle'
    close=stop
    def poll(self):return None,self.status,''
class MediaTests(unittest.TestCase):
    def test_original_phrases_music_video_navigation_and_persistent_ratings(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'playlist.json').write_text(json.dumps(dict(version=1,
                speech=[dict(label='我想喝水',path='water.wav'),dict(label='我需要帮助',path='help.wav')],
                music=[dict(label='曲目一',path='one.wav'),dict(label='曲目二',path='two.wav')],
                videos=[dict(label='视频一',path='video1',frames=20,fps=10),dict(label='视频二',path='video2',frames=20,fps=10)])),encoding='utf8')
            audio=Audio();video=Video();router=MediaRouter(root,root/'ratings.json',audio=audio,video=video)
            self.assertEqual(router.choose('speech',0,0),'speech');self.assertEqual(audio.starts,['water.wav'])
            router.choose('speech',2,1);self.assertEqual(audio.starts,['water.wav','help.wav'])
            self.assertEqual(router.choose('media',0,2),'video');self.assertEqual(video.starts,['video1'])
            self.assertEqual(router.choose('video',0,3),'video_nav')
            self.assertEqual(router.choose('video_nav',2,4),'video');self.assertEqual(video.starts[-1],'video2')
            self.assertEqual(router.choose('video_rate',0,5),'video');router.close()
            self.assertEqual(json.loads((root/'ratings.json').read_text(encoding='utf8')),{'video2':'好'})
            restored=MediaRouter(root,root/'ratings.json',audio=Audio(),video=Video())
            restored.choose('video_nav',2,5.5)
            self.assertEqual(restored.rating,'好');self.assertEqual(restored.choose('media',2,6),'music')
            self.assertEqual(restored.choose('music',1,7),'music');self.assertEqual(restored.audio.starts,['two.wav'])
            restored.stop();self.assertEqual(restored.audio.status,'idle');restored.close()
if __name__=='__main__':unittest.main()

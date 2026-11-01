"""Render shipped HDMI pages from actual public replay and generated music PCM."""
import argparse,json
from pathlib import Path
from PIL import Image
from vision_demo.signal_source import PublicReplay
from vision_demo.signal_core import normalize_eeg,PAGES,MusicPolicy
from vision_demo.signal_audio import PlaybackAnalysis
from vision_demo.signal_render import SignalPresenter
HERE=Path(__file__).resolve().parent
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--assets',type=Path,default=HERE/'build/signal_assets');p.add_argument('--output',type=Path,required=True);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
 replay=PublicReplay(a.assets/'replay');render=SignalPresenter();policy=MusicPolicy();policy.arm();tracks=json.loads((a.assets/'music/catalog.json').read_text(encoding='utf-8'))['tracks']
 for seconds in range(0,91):
  f=normalize_eeg(replay.snapshot(seconds));policy.update(f,seconds);render.render('fatigue',f,{},None,seconds)
 genre=policy.current or 'steady';track=tracks[genre];pcm=PlaybackAnalysis()
 for seconds in range(1,7):audio=pcm.update(dict(phase='feeding',source=str(a.assets/'music'/track['path']),position_frames_estimate=seconds*48000,revision=1),seconds)
 pcm.close();music=dict(reason=policy.reason,title=track['title'],genre=policy.current,confirmations=policy.confirmations,events=policy.events,player=dict(phase='stopped',position_frames_estimate=0))
 # Display test uses real source PCM with reference FFT; no speaker/PL execution is claimed.
 audio['backend']='PS NumPy参考 / 素材分析预览';sheet=Image.new('RGB',(1280,1440))
 for k,page in enumerate(PAGES):
  rgb=render.render(page,f,music,audio,90);image=Image.fromarray(rgb);image.save(a.output/(page+'.png'));sheet.paste(image.resize((640,360)),((k%2)*640,(k//2)*360))
  image.resize((1366,768)).save(a.output/(page+'-1366.png'))
 sheet.crop((0,0,1280,720)).save(a.output/'four-pages.png')
 print(a.output.resolve())

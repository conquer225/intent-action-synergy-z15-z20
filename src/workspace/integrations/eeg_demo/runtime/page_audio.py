"""Candidate audio routing for the existing unified controller; no PL loading."""
import math
import hashlib
from pathlib import Path
import wave

from audio_session import PcmSession


def create_page_audio(config, display_overlay):
    bit = Path(display_overlay)
    expected = {
        bit:'ef60c903c519efb7b4eb5dbcadca1594208f5049207e1a92e422b918dbaae2f6',
        bit.with_suffix('.hwh'):'e7c3bcb9024393fba331f6b0c9b85b4a488832555c06309142703b308819767d'}
    records = [config['player'],config['music'],*config['phrases'].values(),*config['videos'].values()]
    for row in records:
        expected[Path(row['path'])] = row['sha256']
    for path,digest in expected.items():
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError('Verified audio artifact changed: '+str(path))
    # Header rejection must also close the unused process-owner thread.
    session = PcmSession([config['player']['path']])
    try:
        return PageAudio(session,{int(k):v['path'] for k,v in config['phrases'].items()},
                         config['music']['path'],{k:v['path'] for k,v in config['videos'].items()},
                         volume=config['volume_percent'])
    except (OSError,ValueError,wave.Error):
        session.close()
        raise


class PageAudio:
    def __init__(self, session, phrases, music, videos, volume=40):
        self.session = session
        self.phrases = {region:Path(path).resolve(strict=True) for region,path in phrases.items()}
        self.music = Path(music).resolve(strict=True)
        self.videos = {ident:Path(path).resolve(strict=True) for ident,path in videos.items()}
        if set(self.phrases) != {0,2}:
            raise ValueError('Expected water/help speech regions')
        self.frames = {}
        for path in {*self.phrases.values(),self.music,*self.videos.values()}:
            with wave.open(str(path),'rb') as wav:
                if (wav.getframerate(),wav.getnchannels(),wav.getsampwidth(),wav.getcomptype()) != (48000,2,2,'NONE'):
                    raise ValueError('Audio asset must be prepared as PCM16 stereo, 48 kHz')
                length = wav.getnframes()
                if not 0 < length <= 600*48000:
                    raise ValueError('Invalid prepared audio length')
                self.frames[path] = length
        self.volume = 40
        self.volume_dirty = False
        self.set_volume(volume)
        self.key = None
        self.kind = None
        self.speech_key = None
        self.seen_speech = None
        self.last_video = None
        self.video_loop = 0
        self.reason = 'idle'
        self.video_position = None

    def set_volume(self, value):
        if type(value) is not int or not 0 <= value <= 100:
            raise ValueError('Volume must be an integer percentage, 0..100')
        if value != self.volume:
            self.volume_dirty = True
            self.volume = value

    def service(self, controller, video_id=None, video_position_s=0., video_running=False, blocked=False):
        if type(video_position_s) not in (int,float) or not math.isfinite(video_position_s) or video_position_s<0:
            raise ValueError('Invalid presented video position')
        view = self.session.snapshot()
        receipt = controller.last_selection
        speech = ((receipt['page_id'],receipt['monotonic'],receipt['region'])
                  if controller.page=='speech' and receipt and receipt['page_id']==controller.page_id
                  and receipt['region'] in self.phrases else None)
        if controller.page != 'speech':
            self.speech_key = None
        if blocked:
            # A selection made during calibration/pause must not speak later by surprise.
            if speech:
                self.seen_speech = speech
            self.speech_key = None
        elif speech and speech != self.seen_speech:
            self.seen_speech = self.speech_key = speech
        key = path = kind = None
        position = 0
        self.video_position = None
        if blocked:
            self.reason = 'display_paused_or_calibrating'
        elif controller.page == 'speech' and self.speech_key:
            kind = 'speech'
            key = (kind,self.speech_key)
            path = self.phrases[self.speech_key[2]]
        elif controller.page == 'music':
            kind = 'music'
            choice = (receipt['monotonic'] if receipt and receipt['page_id']==controller.page_id else None)
            key = (kind,controller.page_id,controller.song_index,choice)
            path = self.music
        elif controller.page == 'video' and video_running:
            path = self.videos.get(video_id)
            if path is None:
                self.reason = 'video_has_no_prepared_audio'
            else:
                if self.last_video and self.last_video[0]==video_id and video_position_s < self.last_video[1]-.05:
                    self.video_loop += 1
                self.last_video = (video_id,video_position_s)
                kind = 'video'
                key = (kind,video_id,self.video_loop)
                position = int(video_position_s*48000)
                self.video_position = position
        else:
            self.reason = 'page_without_audio_or_video_paused'
        if path is not None:
            self.reason = 'selected'
            if key == self.key and self.volume_dirty and kind != 'video':
                position = view.get('position_frames_estimate',0)
            if position >= self.frames[path]:
                key = path = kind = None
                self.reason = 'audio_finished_before_video'
        if key != self.key:
            if path is None:
                if self.key is not None:
                    self.session.stop()
            else:
                self.session.play(path,start_frame=position,volume=self.volume)
            self.key,self.kind = key,kind
        elif path is not None and self.volume_dirty and view['phase'] not in ('completed','error'):
            self.session.play(path,start_frame=position,volume=self.volume)
        self.volume_dirty = False
        return self.snapshot()

    def snapshot(self):
        view = self.session.snapshot()
        offset = (1000*(view['position_frames_estimate']-self.video_position)/48000
                  if self.kind=='video' and self.video_position is not None
                  and 'position_frames_estimate' in view else None)
        return dict(backend='candidate_hdmi_pcm',volume_percent=self.volume,kind=self.kind,
                    reason=self.reason,player=view,video_offset_estimate_ms=offset,
                    speaker_latency_measured=False)

    def close(self):
        self.session.close()

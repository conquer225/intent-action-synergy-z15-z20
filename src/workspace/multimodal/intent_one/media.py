"""Eye media navigation reuses original players and durable rating storage."""
import json
from pathlib import Path
from . import vendor
from guardianloop_system.media_library import MediaLibrary,RatingWriter

PAGES=frozenset(('more','speech','media','video','video_nav','video_rate','music'))
LABELS={'more':['交流表达','多媒体','返回主页'],'speech':['我想喝水','返回','我需要帮助'],
        'media':['观看视频','返回','选择音乐'],'video':['翻动视频','','评价'],
        'video_nav':['上一条','返回观看','下一条'],'video_rate':['好','返回观看','厌倦'],
        'music':['播放 / 停止','下一首','返回']}

class MediaRouter:
    def __init__(self,directory,ratings_path,audio=None,video=None,library_state=None,audio_device=None,prepared_root=None):
        from media_menu import Catalog
        from media_players import AudioPlayer,VideoPlayer
        self.catalog=Catalog(directory);self.audio=audio or AudioPlayer(audio_device or self.catalog.device)
        self.video=video or VideoPlayer();self.video_index=self.song_index=0;self.picture=None;self.frame=-1
        self.detail=self.catalog.error;self.paused=False;self.records=[]
        for asset in self.catalog.groups['videos']:
            self.records.append(dict(id=asset.path.relative_to(self.catalog.root).as_posix(),name=asset.label,
                                     cache=str(asset.path),download='',source='local_playlist',asset=asset,kind='jpeg'))
        if library_state and Path(library_state).is_file():
            data=json.loads(Path(library_state).read_text(encoding='utf8'))
            for row in data.get('playlist',[]):
                if not isinstance(row,dict) or not all(isinstance(row.get(k),str) and row[k] for k in ('id','name','cache')):raise ValueError('invalid prepared video entry')
                self.records.append(dict(row,kind='cache'))
        if prepared_root:
            root=Path(prepared_root)
            for cache in sorted((root/'assets').glob('*/cache')):
                if not (cache/'manifest.json').is_file():continue
                ident=cache.parent.name
                if any(row['id']==ident for row in self.records):continue
                ready=cache.parent/'ready.json';metadata=json.loads(ready.read_text(encoding='utf8')) if ready.is_file() else {}
                self.records.append(dict(id=ident,name=metadata.get('name',{'sd01':'小奶猫（SD竖版）','sd02':'小狗（SD竖版）'}.get(ident,ident)),
                                         cache=str(cache),download=str(cache.parent/'portrait.mp4'),source='retained_prepared_video',kind='cache'))
        self.library=MediaLibrary(ratings_path)
        self.library.replace(self.records);self.writer=RatingWriter(self.library)
    @property
    def rating(self):
        return self.library.ratings.get(self.records[self.video_index]['id']) if self.records else None
    def labels(self,page):
        if page=='music':return ['停止播放' if self.audio.status=='playing' else '播放音乐','下一首','返回']
        return list(LABELS[page])
    def stop(self):
        self.audio.stop();self.video.stop();self.picture=None;self.frame=-1
        if hasattr(self,'cache_video'):self.cache_video.stop()
    def start_video(self):
        if not self.records:self.detail='暂无视频；原素材文件保留，请指定媒体目录';return False
        row=self.records[self.video_index];self.detail=row['name'];self.picture=None;self.frame=-1
        if row['kind']=='cache':
            if not hasattr(self,'cache_video'):
                from .video_cache import CacheVideo
                self.cache_video=CacheVideo()
            self.video.stop();return self.cache_video.start(Path(row['cache']))
        if hasattr(self,'cache_video'):self.cache_video.stop()
        return self.video.start(row['asset'])
    def play_song(self):
        songs=self.catalog.groups['music']
        if not songs:self.detail='暂无音乐，请配置playlist.json';return
        asset=songs[self.song_index];self.detail=asset.label
        if not self.audio.start(asset.path):self.detail=self.audio.error
    def choose(self,page,index,now):
        if self.paused:return page
        if page=='more':return ('speech','media','home')[index]
        if page=='speech':
            if index==1:self.audio.stop();return 'more'
            label=LABELS['speech'][index];asset=next((x for x in self.catalog.groups['speech'] if x.label==label),None)
            if asset is None:self.detail='缺少这条表达的音频：'+label
            elif self.audio.start(asset.path):self.detail='正在发声：'+label
            else:self.detail=self.audio.error
        elif page=='media':
            self.stop()
            if index==0:return 'video' if self.start_video() else 'media'
            return ('video','more','music')[index]
        elif page=='video':return ('video_nav','video','video_rate')[index]
        elif page=='video_nav':
            if index!=1 and self.records:
                self.video_index=(self.video_index+(-1 if index==0 else 1))%len(self.records)
                self.start_video()
            return 'video'
        elif page=='video_rate':
            if index!=1 and self.records:
                self.writer.submit(self.records[self.video_index]['id'],('好','', '厌倦')[index]);self.detail='评价已记录'
            return 'video'
        elif page=='music':
            if index==2:self.audio.stop();return 'media'
            if index==1:
                if self.catalog.groups['music']:self.song_index=(self.song_index+1)%len(self.catalog.groups['music'])
                self.audio.stop();self.play_song()
            elif self.audio.status=='playing':self.audio.stop();self.detail='已停止，选择播放可重新开始'
            else:self.play_song()
        return page
    def tick(self):
        result=self.audio.poll()
        if result:self.detail=result[1] or '音频播放结束，等待选择'
        player=self.cache_video if hasattr(self,'cache_video') and self.cache_video.status!='idle' else self.video
        frame,status,error=player.poll()
        if frame is not None:self.frame,self.picture=frame
        if error:self.detail=error
        if self.writer.error:raise RuntimeError('视频评价保存失败：'+self.writer.error)
    def pause(self,page):
        self.stop()
        if hasattr(self,'cache_video'):self.cache_video.stop()
        if page in ('video','video_nav','video_rate'):
            self.paused=False;self.detail='视频已退出';return 'media'
        self.paused=not self.paused;self.detail='已暂停' if self.paused else '已继续，请重新选择';return page
    def snapshot(self):
        song=self.catalog.groups['music'][self.song_index].label if self.catalog.groups['music'] else None
        return dict(detail=self.detail,audio_status=self.audio.status,video_index=self.video_index,
                    video_name=self.records[self.video_index]['name'] if self.records else None,rating=self.rating,
                    song=song,paused=self.paused,frame=self.frame,video_count=len(self.records))
    def close(self):
        try:self.stop()
        finally:
            if hasattr(self,'cache_video'):self.cache_video.close()
            self.writer.close()

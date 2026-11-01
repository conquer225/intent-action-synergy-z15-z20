"""Prepared video cache adapter. Original bounded decoder retains its storage rules."""
import time
from PIL import Image
from . import vendor
from chunk_cache import BoundedChunks

class CacheVideo:
    def __init__(self,source_factory=BoundedChunks,clock=time.monotonic):
        self.factory=source_factory;self.clock=clock;self.source=None;self.block=None;self.cursor=0
        self.status='idle';self.error='';self.last_index=-1
    def start(self,path):
        self.stop();self.error=''
        try:
            self.source=self.factory(path,loop=True)
            if self.source.meta['format'] not in ('gl-bgr24-lz4-v1','gl-bgr24-xor-lz4-v1'):raise ValueError('当前入口使用已准备的BGR视频缓存')
            self.started=self.clock();self.cursor=0;self.last_index=-1;self.status='playing';return True
        except (OSError,ValueError) as exc:
            self.stop();self.status='error';self.error=str(exc);return False
    def poll(self):
        if self.status!='playing':return None,self.status,self.error
        try:
            wanted=max(0,int((self.clock()-self.started)*self.source.meta['fps']))
            for _ in range(8):
                if self.block is None:
                    try:self.block=self.source.acquire(timeout=0)
                    except TimeoutError:return None,self.status,self.error
                    if self.block is None:self.status='complete';return None,self.status,''
                slot,count=self.block
                if wanted<self.cursor+count:
                    if wanted==self.last_index:return None,self.status,''
                    raw=self.source.slots[slot][wanted-self.cursor].tobytes()
                    picture=Image.frombytes('RGB',(self.source.meta['width'],self.source.meta['height']),raw,'raw','BGR')
                    self.last_index=wanted;return (wanted,picture),self.status,''
                self.source.release(slot);self.block=None;self.cursor+=count
            return None,self.status,''
        except (OSError,ValueError) as exc:self.error=str(exc);self.status='error';return None,self.status,self.error
    def stop(self):
        if self.source:
            if self.block is not None:self.source.release(self.block[0]);self.block=None
            self.source.close();self.source=None
        self.status='idle'
    close=stop

"""Stable video IDs and durable ratings; never deletes uploaded/liked media."""
import json
from pathlib import Path
import threading
import queue
import os
import time
from contextlib import contextmanager


@contextmanager
def rating_lock(path):
    """Cross-process lock; a crashed writer leaves an explicit inspection marker."""
    lock=path.with_suffix('.lock');deadline=time.monotonic()+1
    while True:
        try:
            fd=os.open(str(lock),os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
            break
        except FileExistsError:
            if time.monotonic()>=deadline:raise TimeoutError('Rating store is busy; inspect retained lock')
            time.sleep(.01)
    try:
        os.close(fd)
        yield
    finally:lock.unlink()


class MediaLibrary:
    def __init__(self,path):
        self.path=Path(path);self.lock=threading.RLock();self.videos=[]
        self.ratings=json.loads(self.path.read_text(encoding='utf-8')) if self.path.exists() else {}
        if not isinstance(self.ratings,dict):raise ValueError('Invalid ratings database')

    def replace(self,videos):
        if len({v['id'] for v in videos})!=len(videos):raise ValueError('Duplicate video ID')
        self.videos=list(videos)

    def rate(self,identifier,value):
        if value not in ('好','厌倦') or not any(v['id']==identifier for v in self.videos):
            raise ValueError('Unknown video or rating')
        with self.lock:
            self.path.parent.mkdir(parents=True,exist_ok=True)
            with rating_lock(self.path):
                updated=json.loads(self.path.read_text(encoding='utf-8')) if self.path.exists() else {}
                if not isinstance(updated,dict):raise ValueError('Invalid ratings database')
                updated[identifier]=value
                part=self.path.with_suffix('.json.part');part.write_text(json.dumps(updated,ensure_ascii=False),encoding='utf-8')
                part.replace(self.path);self.ratings=updated

    def snapshot(self):
        with self.lock:
            if self.path.exists():self.ratings=json.loads(self.path.read_text(encoding='utf-8'))
            def prepared(video):
                path=Path(video['cache'])/'manifest.json'
                if not path.exists():return False
                data=json.loads(path.read_text(encoding='utf-8'))
                return (data.get('width'),data.get('height'))==(288,512) and data.get('fps') in (10,20)
            return [dict(id=v['id'],name=v['name'],rating=self.ratings.get(v['id']),
                         prepared=prepared(v),
                         downloadable=Path(v['download']).is_file(),
                         bytes=Path(v['download']).stat().st_size if Path(v['download']).is_file() else 0,
                         source=v['source'],phone_file_saved=False) for v in self.videos]


class RatingWriter:
    def __init__(self,library):
        self.library=library;self.jobs=queue.Queue(maxsize=32);self.error=None
        self.thread=threading.Thread(target=self._run,name='system-rating-store',daemon=True)
        self.thread.start()

    def _run(self):
        while True:
            item=self.jobs.get()
            try:
                if item is None:return
                self.library.rate(*item)
            except (OSError,ValueError) as error:self.error=str(error)
            finally:self.jobs.task_done()

    def submit(self,identifier,value):
        if self.error:raise RuntimeError('Rating persistence failed: '+self.error)
        self.jobs.put_nowait((identifier,value))

    def close(self):
        self.jobs.put(None,timeout=1);self.thread.join(timeout=3)
        if self.thread.is_alive():raise RuntimeError('Rating writer did not stop')
        if self.error:raise RuntimeError(self.error)

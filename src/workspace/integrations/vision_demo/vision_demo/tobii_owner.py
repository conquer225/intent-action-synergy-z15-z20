"""Follow the live eye owner, or acquire its exclusive lock for image-only input."""
from pathlib import Path
import shutil
import subprocess
import tempfile
from .sources import PgmSource
from .session import Frame


class TobiiImages:
    def __init__(self,generation,shared_directory=None,binary=None):
        self.process=None;self.temporary=None;self.log=None;self.reader=None
        self.provider=shared_directory if callable(shared_directory) else lambda:shared_directory
        self.directory=None;self.binary=binary;self.generation=generation;self.sequence=0
        self._bind(self.provider())

    def _bind(self,shared):
        self._release()
        if shared is not None:
            directory=Path(shared)
        else:
            if self.binary is None or not Path(self.binary).is_file():raise RuntimeError('Tobii image worker not installed')
            directory=Path(tempfile.mkdtemp(prefix='guardianloop-vision-',dir='/dev/shm'))
            self.temporary=directory
            self.log=(directory/'usb.log').open('wb')
            self.process=subprocess.Popen([str(self.binary),str(directory)],stdout=self.log,stderr=self.log)
        self.directory=Path(shared) if shared is not None else None
        self.reader=PgmSource(directory,self.generation)

    def read(self,now):
        shared=self.provider();directory=Path(shared) if shared is not None else None
        if directory!=self.directory:self._bind(shared)
        if self.process is not None and self.process.poll() is not None:
            raise RuntimeError('Tobii image owner exited (code %s); verify USB connection and current owner'%self.process.returncode)
        self.reader.generation=self.generation
        frame=self.reader.read(now)
        if frame is None:return None
        self.sequence+=1
        return Frame(frame.source,self.generation,self.sequence,frame.captured,frame.rgb)

    def _release(self):
        if self.process is not None and self.process.poll() is None:
            self.process.terminate()
            try:self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.kill();self.process.wait(timeout=2)
        if self.log:self.log.close()
        if self.temporary:shutil.rmtree(self.temporary)
        self.process=None;self.temporary=None;self.log=None;self.reader=None

    def close(self):self._release()

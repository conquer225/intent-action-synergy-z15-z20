"""Non-blocking eye-menu client; pending actions are discarded on connection loss."""
import queue,threading,time
from .visual_server import DemoClient
from .wireless_only import require_wireless


class Z15VisualClient:
    def __init__(self,host,token):
        self.host,self.token=host,token
        self.pending=queue.Queue(maxsize=8);self.stop=threading.Event();self.lock=threading.Lock()
        self.latest={};self.received=-float('inf')
        self.thread=threading.Thread(target=self._work,daemon=True);self.thread.start()

    def send(self,name):
        current=self.snapshot()
        if not current.get('connected'):return False
        try:self.pending.put_nowait((time.monotonic(),name,current.get('session'),current.get('epoch')));return True
        except queue.Full:return False

    def snapshot(self):
        with self.lock:return dict(self.latest,connected=time.monotonic()-self.received<2)

    def _clear(self):
        while True:
            try:self.pending.get_nowait()
            except queue.Empty:return

    def _work(self):
        while not self.stop.is_set():
            try:
                require_wireless(self.host)
                with DemoClient(self.host,token=self.token) as client:
                    self._clear()
                    while not self.stop.is_set():
                        state=client.status()
                        try:created,name,session,epoch=self.pending.get_nowait()
                        except queue.Empty:pass
                        else:
                            if (time.monotonic()-created<2 and session==state.get('session') and epoch==state.get('epoch')):
                                state=client.command(name)
                        with self.lock:self.latest,self.received=state,time.monotonic()
                        self.stop.wait(.08)
            except (OSError,ValueError,RuntimeError,EOFError):
                with self.lock:self.latest={};self.received=-float('inf')
                self._clear();self.stop.wait(.5)

    def close(self):self.stop.set();self.thread.join(3)

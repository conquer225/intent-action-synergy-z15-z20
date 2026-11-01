"""Nonblocking auxiliary publisher with fresh sessions on reconnect."""
import ipaddress
import socket
import threading
from .service import FeaturePublisher


class ReconnectingFeatures:
    def __init__(self,host,port=9020,*,retry_seconds=.5):
        ipaddress.ip_address(host)
        if type(port) is not int or not 1024<=port<=65535 or port==9000:
            raise ValueError('use the auxiliary feature port, never S3 port 9000')
        if not .05<=retry_seconds<=30:raise ValueError('retry delay outside range')
        self.host,self.port,self.retry_seconds=host,port,retry_seconds
        self.lock,self.stopped=threading.Lock(),threading.Event()
        self.client,self.thread=None,None
        self.connections,self.dropped=0,0

    @property
    def connected(self):
        with self.lock:
            return self.client is not None and not self.client.peer.stopped.is_set()

    def start(self):
        if self.thread is not None:raise RuntimeError('client already started')
        self.thread=threading.Thread(target=self._run,name='z15-auxiliary-link',daemon=True)
        self.thread.start()

    def _run(self):
        while not self.stopped.is_set():
            with self.lock:client=self.client
            if client is None or client.peer.stopped.is_set():
                if client is not None:client.close()
                with self.lock:self.client=None
                try:
                    new=FeaturePublisher(socket.create_connection((self.host,self.port),timeout=2))
                    new.start()
                except OSError:
                    self.stopped.wait(self.retry_seconds);continue
                if self.stopped.is_set():new.close();break
                with self.lock:
                    self.client=new;self.connections+=1
            self.stopped.wait(self.retry_seconds)
        with self.lock:
            client,self.client=self.client,None
        if client is not None:client.close()

    def offer_features(self,*args,**kwargs):
        if not self.lock.acquire(blocking=False):
            self.dropped+=1;return False
        try:client=self.client
        finally:self.lock.release()
        if client is None or client.peer.stopped.is_set():
            self.dropped+=1;return False
        return client.offer_features(*args,**kwargs)

    def result(self,task):
        with self.lock:client=self.client
        if client is None or client.peer.stopped.is_set():return None
        return client.results.get(task)

    def close(self):
        self.stopped.set()
        if self.thread is not None:self.thread.join(3)

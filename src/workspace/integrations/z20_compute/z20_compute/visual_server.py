"""Two bounded private-LAN channels; only the renderer may submit JPEG frames."""
import hmac
import socket
import socketserver
import threading
import uuid
from .visual_wire import read_json,write_json,read_frame,jpeg_dimensions


class _Server(socketserver.ThreadingTCPServer):
    allow_reuse_address=True
    daemon_threads=True
    block_on_close=False
    request_queue_size=8


class _Control(socketserver.StreamRequestHandler):
    def handle(self):
        self.request.settimeout(3)
        owner=self.server.owner;role=session=None
        client=uuid.uuid4().hex
        if not owner.slots.acquire(False):return
        try:
            hello=read_json(self.rfile)
            if not owner.authorized(hello):write_json(self.wfile,dict(ok=False));return
            role=hello.get('role')
            if role not in ('controller','renderer'):raise ValueError('unknown role')
            session=owner.state.attach_renderer() if role=='renderer' else owner.state.session
            write_json(self.wfile,dict(ok=True,session=session,epoch=owner.state.epoch))
            while True:
                row=read_json(self.rfile)
                if role=='renderer' and not owner.state.touch(session):raise ValueError('renderer replaced')
                if row.get('op')=='status':result=owner.state.snapshot()
                elif row.get('op')=='sound_input' and role=='controller':result=owner.state.accept_sound(row)
                elif row.get('op')=='command' and role=='controller':
                    with owner.state.lock:
                        if row.get('session')!=owner.state.session or row.get('epoch')!=owner.state.epoch:
                            result=dict(owner.state.snapshot(),accepted=False)
                        else:result=owner.state.command(client,row.get('sequence'),row.get('name'))
                else:raise ValueError('operation not allowed')
                write_json(self.wfile,result)
        except (OSError,EOFError,ValueError,TypeError):pass
        finally:
            if role=='renderer' and session:owner.state.detach_renderer(session)
            owner.slots.release()


class _Frames(socketserver.StreamRequestHandler):
    def handle(self):
        self.request.settimeout(3)
        owner=self.server.owner
        if not owner.slots.acquire(False):return
        try:
            hello=read_json(self.rfile)
            if not owner.authorized(hello) or hello.get('session')!=owner.state.session:
                write_json(self.wfile,dict(ok=False));return
            session=hello['session'];write_json(self.wfile,dict(ok=True))
            while True:
                meta,jpeg=read_frame(self.rfile)
                jpeg_dimensions(jpeg)  # Reject oversized compressed dimensions before decoding.
                accepted=False
                if meta['session']==session:
                    accepted=owner.state.accept_frame(session,meta['epoch'],meta['sequence'],jpeg)
                write_json(self.wfile,dict(accepted=accepted,sequence=meta['sequence']))
        except (OSError,EOFError,ValueError,TypeError):pass
        finally:owner.slots.release()


class DemoServer:
    def __init__(self,state,bind,control_port=9022,frame_port=9023,*,token):
        if not isinstance(token,str) or not token:raise ValueError('private demo token required')
        self.state,self.token=state,token
        self.slots=threading.BoundedSemaphore(8)
        self.control=_Server((bind,control_port),_Control)
        try:self.frames=_Server((bind,frame_port),_Frames)
        except BaseException:self.control.server_close();raise
        for server in (self.control,self.frames):server.owner=self
        self.control_port=self.control.server_address[1]
        self.frame_port=self.frames.server_address[1]
        self.threads=[]

    def authorized(self,row):
        token=row.get('token')
        return isinstance(token,str) and hmac.compare_digest(token,self.token)

    def __enter__(self):
        for server in (self.control,self.frames):
            thread=threading.Thread(target=server.serve_forever,kwargs=dict(poll_interval=.05),daemon=True)
            self.threads.append(thread);thread.start()
        return self

    def close(self):
        for server in (self.control,self.frames):
            if self.threads:server.shutdown()
            server.server_close()
        for thread in self.threads:thread.join(2)
        self.threads=[]

    def __exit__(self,*_):self.close()


class DemoClient:
    def __init__(self,host,port=9022,*,token,role='controller',timeout=2):
        self.sock=socket.create_connection((host,port),timeout=timeout)
        self.sock.setsockopt(socket.IPPROTO_TCP,socket.TCP_NODELAY,1)
        self.stream=self.sock.makefile('rwb');self.lock=threading.RLock();self.sequence=0
        try:
            write_json(self.stream,dict(token=token,role=role))
            hello=read_json(self.stream)
            if not hello.get('ok'):raise PermissionError('demo authentication rejected')
            self.session=hello['session']
            self.epoch=hello['epoch']
        except BaseException:self.close();raise

    def request(self,row):
        with self.lock:
            write_json(self.stream,row);result=read_json(self.stream)
            self.session,self.epoch=result.get('session',self.session),result.get('epoch',self.epoch)
            return result

    def command(self,name):
        with self.lock:
            self.sequence+=1
            return self.request(dict(op='command',sequence=self.sequence,name=name,session=self.session,epoch=self.epoch))

    def status(self):return self.request(dict(op='status'))
    def sound_input(self,vector,*,source,window_id,valid=True):
        return self.request(dict(op='sound_input',session=self.session,epoch=self.epoch,
            vector=vector,source=source,window_id=window_id,valid=valid))
    def close(self):self.stream.close();self.sock.close()
    def __enter__(self):return self
    def __exit__(self,*_):self.close()

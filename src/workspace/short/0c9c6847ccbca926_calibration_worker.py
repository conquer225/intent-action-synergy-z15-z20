"""Nonblocking UI/USB boundary; each press owns one finite native session."""
import json
import os
from pathlib import Path
import signal
import subprocess
import time
import uuid

class CalibrationRestart:
    """Stop the active session and gate replacement on actual process exit."""
    def __init__(self, timeout=12):
        self.timeout = timeout
        self.requested_at = None

    @property
    def pending(self):
        return self.requested_at is not None

    def request(self, state, worker, menu, selection, now):
        if self.pending or state.phase != "selection":
            return False
        if menu is not None:
            menu.close()
        if selection is not None:
            selection.clear_pending()
        if worker is not None:
            worker.abort()
        self.requested_at = now
        state.phase = "restarting"
        state.detail = "正在结束上一轮采样，随后自动重新标定"
        return True

    def poll(self, worker, now):
        if not self.pending:
            return None
        if worker is None or worker.process.poll() is not None:
            self.cancel()
            return "ready"
        if now-self.requested_at >= self.timeout:
            self.cancel()
            return "timeout"
        return None

    def cancel(self):
        self.requested_at = None

class Worker:
    def __init__(self, root, width, height, relaxed=False, diagnostic=False, validation_model=None, selection_test=False, locate=False, calibration_points=3,relative=False):
        if calibration_points not in (3,5,9):raise ValueError("Calibration point count must be 3, 5 or 9")
        self.directory=Path(root)/"captures"/("cal_"+uuid.uuid4().hex)
        self.directory.mkdir(mode=0o700)
        self.log=open(self.directory/"worker.log","wb")
        options=(["--validate-model",str(validation_model)] if validation_model else
                 ["--locate"] if locate else ["--check-tracking"] if diagnostic else ["--relative-selection"] if relative else [{3:"--selection-test",5:"--selection-test5",9:"--selection-test9"}[calibration_points]] if selection_test else ["--relaxed"] if relaxed else [])
        self.process=subprocess.Popen([str(Path(root)/"is4-calibration"),
            str(self.directory),str(width),str(height)]+options,stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,stderr=self.log,start_new_session=True)
        os.set_blocking(self.process.stdout.fileno(),False)
        self.buffer=bytearray()
        self.started=time.monotonic()
        self.done=False
        self.result=None
        self.aborted=False

    def command(self, words):
        if self.process.poll() is not None:
            raise RuntimeError("眼动采样进程已退出")
        self.process.stdin.write((words+"\n").encode())
        self.process.stdin.flush()

    def poll(self):
        events=[]
        while True:
            try: chunk=os.read(self.process.stdout.fileno(),4096)
            except BlockingIOError: break
            if not chunk: break
            self.buffer.extend(chunk)
        if len(self.buffer)>65536: raise RuntimeError("采样状态消息过长")
        while b"\n" in self.buffer:
            line,_,rest=self.buffer.partition(b"\n"); self.buffer=bytearray(rest)
            if line:
                event=json.loads(line)
                if event.get("kind")=="result": self.result=event
                else: events.append(event)
        # Success is delayed until native cleanup/exit has also succeeded.
        code=self.process.poll()
        if code is not None and not self.done:
            self.done=True
            if code==0 and self.result:events.append(self.result)
            elif not any(e.get("kind")=="error" for e in events):
                events.append({"kind":"error","code":code})
        return events

    def close(self):
        if self.process.poll() is None:
            os.killpg(self.process.pid,signal.SIGTERM)
            try:self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(self.process.pid,signal.SIGKILL)
                self.process.wait(timeout=2)
                print("worker_cleanup_timeout; device state needs recheck",flush=True)
        self.process.stdin.close();self.process.stdout.close();self.log.close()

    def abort(self):
        if self.process.poll() is None and not self.aborted:
            self.aborted=True
            os.killpg(self.process.pid,signal.SIGTERM)

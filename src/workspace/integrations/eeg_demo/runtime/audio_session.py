"""Single PCM child owner; blocking process operations stay off the display loop."""
import collections
import json
from pathlib import Path
import subprocess
import threading


class PcmSession:
    def __init__(self, player):
        self.player = tuple(str(arg) for arg in player)
        if not self.player:
            raise ValueError('Missing PCM player command')
        self.condition = threading.Condition()
        self.revision = 0
        self.handled = 0
        self.desired = None
        self.closed = False
        self.process = None
        self.readers = []
        self.view = dict(phase='idle', revision=0, pid=None, audible_verified=False)
        self.errors = collections.deque(maxlen=16)
        self.worker = threading.Thread(target=self._run, name='hdmi-audio-owner', daemon=True)
        self.worker.start()

    def play(self, path, start_frame=0, volume=10):
        path = Path(path).resolve(strict=True)
        if not path.is_file() or type(start_frame) is not int or not 0 <= start_frame < 600*48000:
            raise ValueError('Invalid local PCM asset or start position')
        if type(volume) is not int or not 0 <= volume <= 100:
            raise ValueError('Invalid PCM volume')
        return self._request((str(path), start_frame, volume))

    def stop(self):
        return self._request(None)

    def _request(self, desired):
        with self.condition:
            if self.closed:
                raise RuntimeError('Audio session is closed')
            self.desired = desired
            self.revision += 1
            self.condition.notify()
            return self.revision

    def snapshot(self):
        with self.condition:
            return dict(self.view, requested_revision=self.revision,
                        worker_alive=self.worker.is_alive(), errors=list(self.errors))

    def _read(self, pipe, revision, status):
        try:
            while True:
                line = pipe.readline(4097)
                if not line:
                    break
                if len(line) > 4096:
                    raise ValueError('PCM player report exceeds 4096 bytes')
                if not status:
                    with self.condition:
                        self.errors.append(line.decode('utf-8', errors='replace').strip())
                    continue
                row = json.loads(line)
                if not isinstance(row, dict) or row.get('phase') not in ('feeding', 'stopped', 'completed', 'error'):
                    raise ValueError('Invalid PCM player phase')
                position = row['position_frames_estimate']
                if type(position) is not int or not 0 <= position <= 600*48000:
                    raise ValueError('Invalid PCM player position')
                with self.condition:
                    if self.view['revision'] == revision:
                        self.view.update(phase=row['phase'], position_frames_estimate=position,
                                         underruns=row['underruns'], audible_verified=False)
        except (OSError, ValueError, KeyError) as error:
            with self.condition:
                self.errors.append(str(error))
                if self.view['revision'] == revision:
                    self.view.update(phase='error', error=str(error))
        finally:
            pipe.close()

    def _finish_child(self, stop):
        child = self.process
        if child is None:
            return
        if stop and child.poll() is None:
            child.terminate()
        # Never SIGKILL a process which may still own active PCM hardware.
        # On timeout the owner remains visible and the caller must retain PL.
        child.wait(timeout=2)
        for reader in self.readers:
            reader.join(timeout=1)
            if reader.is_alive():
                raise RuntimeError('PCM report reader did not finish')
        with self.condition:
            self.view.update(pid=None, returncode=child.returncode)
            if stop:
                self.view['phase'] = 'stopped'
            elif child.returncode or self.view['phase'] not in ('completed', 'stopped'):
                self.view.update(phase='error', error='PCM player exited without successful completion')
        self.process = None
        self.readers = []

    def _run(self):
        try:
            while True:
                with self.condition:
                    self.condition.wait_for(lambda: self.closed or self.revision != self.handled, timeout=.05)
                    revision, desired, closed = self.revision, self.desired, self.closed
                if closed:
                    self._finish_child(stop=True)
                    return
                if revision != self.handled:
                    self._finish_child(stop=True)
                    with self.condition:
                        # Requests during teardown replace the pending request, not queue behind it.
                        revision, desired = self.revision, self.desired
                        if self.closed:
                            continue
                        self.handled = revision
                        self.view = dict(phase='stopped', revision=revision, pid=None, audible_verified=False)
                    if desired is not None:
                        path, position, volume = desired
                        self.process = subprocess.Popen(
                            [*self.player, '--play', path, '--start-frame', str(position), '--volume', str(volume)],
                            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                        with self.condition:
                            self.view.update(phase='starting', pid=self.process.pid, source=path,
                                             position_frames_estimate=position)
                        self.readers = [threading.Thread(target=self._read, args=(pipe, revision, status), daemon=True)
                                        for pipe, status in ((self.process.stdout, True), (self.process.stderr, False))]
                        for reader in self.readers:
                            reader.start()
                elif self.process is not None and self.process.poll() is not None:
                    self._finish_child(stop=False)
        except (OSError, subprocess.TimeoutExpired, RuntimeError) as error:
            with self.condition:
                self.view.update(phase='error', error=str(error))
                self.errors.append(str(error))

    def close(self):
        with self.condition:
            self.closed = True
            self.condition.notify()
        self.worker.join(timeout=5)
        if self.worker.is_alive() or (self.process is not None and self.process.poll() is None):
            raise RuntimeError('PCM child has not stopped; do not unload PL')

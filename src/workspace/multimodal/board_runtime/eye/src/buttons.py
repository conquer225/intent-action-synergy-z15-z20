"""Read the existing Z15 gpio-keys input; no GPIO export or pin configuration."""
import os
from pathlib import Path
import struct
import time

EVENT = struct.Struct("@llHHi")
EV_SYN, EV_KEY, SYN_DROPPED = 0, 1, 3
DEBOUNCE_SECONDS = .05

class Edges:
    """One press per release, with debounce; initially held keys stay unarmed."""
    def __init__(self, codes, held=(), debounce=DEBOUNCE_SECONDS):
        self.debounce = debounce
        self.down = {c:c in held for c in codes}
        self.armed = {c:c not in held for c in codes}
        self.pending = {}

    def advance(self, now):
        pressed = []
        for code,(value,changed) in list(self.pending.items()):
            if now-changed < self.debounce:
                continue
            del self.pending[code]
            if value == self.down[code]:
                continue
            self.down[code] = value
            if not value:
                self.armed[code] = True
            elif self.armed[code]:
                self.armed[code] = False
                pressed.append(code)
        return pressed

    def feed(self, code, value, now):
        # Repeats never trigger; duplicate reports do not restart the debounce.
        if code not in self.down or value not in (0,1):
            return []
        result = self.advance(now)
        value = bool(value)
        pending = self.pending.get(code)
        if pending and pending[0] == value:
            return result
        if value == self.down[code]:
            self.pending.pop(code,None)
        else:
            self.pending[code] = (value,now)
        return result

class Buttons:
    def __init__(self):
        import fcntl
        self.fd = None
        self.buffer = bytearray()
        self.mapping = {}
        root = Path("/proc/device-tree/keys")
        for child in root.iterdir():
            if child.is_dir() and (child/"label").exists():
                label=(child/"label").read_bytes().rstrip(b"\0").decode()
                if label in ("ps_key0","ps_key1"):
                    code=struct.unpack(">I",(child/"linux,code").read_bytes())[0]
                    gpio=struct.unpack(">III",(child/"gpios").read_bytes())
                    expected=12 if label=="ps_key0" else 11
                    if gpio[1:] != (expected,1):
                        raise RuntimeError("Unexpected Z15 button mapping: "+label)
                    self.mapping[code]="start" if label=="ps_key0" else "pause"
        if set(self.mapping.values()) != {"start","pause"}:
            raise RuntimeError("Both Z15 PS buttons are required")
        for event in sorted(Path("/sys/class/input").glob("event*")):
            if (event/"device/name").read_text().strip()=="keys":
                self.fd=os.open("/dev/input/"+event.name,os.O_RDONLY|os.O_NONBLOCK|os.O_CLOEXEC)
                break
        if self.fd is None:
            raise RuntimeError("Z15 gpio-keys input not found")
        try:
            # Linux input timestamps use CLOCK_MONOTONIC for consistent debounce
            # even if the board wall clock is corrected during a session.
            fcntl.ioctl(self.fd,0x400445a0,struct.pack("i",1)) # EVIOCSCLOCKID
            held=bytearray(96)
            fcntl.ioctl(self.fd,0x80604518,held,True) # EVIOCGKEY(96)
            self.edges=Edges(self.mapping,[c for c in self.mapping if held[c//8]&(1<<(c%8))])
        except BaseException:
            self.close()
            raise

    def poll(self, now=None):
        now=time.monotonic() if now is None else now
        while True:
            try:
                chunk=os.read(self.fd,EVENT.size*64)
            except BlockingIOError:
                break
            if not chunk:
                raise RuntimeError("Z15 button device disconnected")
            self.buffer.extend(chunk)
        actions=[]
        while len(self.buffer)>=EVENT.size:
            sec,usec,kind,code,value=EVENT.unpack_from(self.buffer)
            del self.buffer[:EVENT.size]
            stamp=sec+usec/1e6
            if kind==EV_SYN and code==SYN_DROPPED:
                # Never guess a start after the kernel reports lost events.
                raise RuntimeError("Z15 button input queue overflow")
            if kind==EV_KEY:
                actions.extend(self.mapping[c] for c in self.edges.feed(code,value,stamp))
        actions.extend(self.mapping[c] for c in self.edges.advance(now))
        return actions

    def close(self):
        if self.fd is not None:
            os.close(self.fd)
            self.fd=None

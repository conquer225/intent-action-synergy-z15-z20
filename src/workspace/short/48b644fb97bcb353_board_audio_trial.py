"""Authorised finite HDMI audio trial and exact previous-service recovery."""
import argparse
import ctypes as C
import fcntl
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import time

BASE = Path(__file__).resolve().parent
PYTHON = '/usr/local/share/pynq-venv/bin/python3'


def run(*argv):
    return subprocess.check_output(argv, text=True, stderr=subprocess.STDOUT, timeout=35).strip()


def save(name, row):
    target = BASE/name
    pending = target.with_suffix('.tmp')
    pending.write_text(json.dumps(row, indent=2))
    os.replace(pending, target)


def verify(state):
    if Path('/proc/sys/kernel/random/boot_id').read_text().strip() != state['boot']:
        raise RuntimeError('Boot changed; refuse old audio trial')
    for name, expected in state['hashes'].items():
        if hashlib.sha256(Path(name).read_bytes()).hexdigest() != expected:
            raise RuntimeError('Audio/recovery artifact changed: '+name)


def service_pid(unit):
    return int(run('systemctl', 'show', unit, '-p', 'MainPID', '--value'))


def restore(state):
    from pynq import Overlay, PL
    verify(state)
    with (BASE/'recovery.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if (BASE/'runtime_restored.json').exists():
            return
        owner = service_pid(state['unit'])
        if owner and owner != os.getpid():
            # Includes the PCM child, before any possible PL reconfiguration.
            run('systemctl', 'kill', '--kill-who=all', '--signal=SIGTERM', state['unit'])
            deadline = time.monotonic()+10
            while service_pid(state['unit']) == owner and time.monotonic() < deadline:
                time.sleep(.2)
        current = PL.bitfile_name
        allowed = (state['original'], state['candidate'], state['previous_display'])
        if current not in allowed:
            raise RuntimeError('Unknown PL owner during recovery: '+str(current))
        remaining = service_pid(state['unit'])
        if current == state['candidate'] or (remaining and remaining != os.getpid()):
            Overlay(state['original'])
            if PL.bitfile_name != state['original']:
                raise RuntimeError('Emergency original PL restore did not verify')
            if remaining and remaining != os.getpid():
                # The DMA has stopped before the owner's CMA allocation can disappear.
                os.kill(remaining, signal.SIGKILL)
                deadline = time.monotonic()+5
                while service_pid(state['unit']) and time.monotonic() < deadline:
                    time.sleep(.1)
        restored = []
        for record in state['services']:
            unit = record['unit']
            display_config = None
            if any(arg.endswith('/media_player.py') for arg in record['argv']):
                argv = record['argv']
                display_config = Path(argv[argv.index('--state')+1])
                config = json.loads(display_config.read_text())
                starting = dict(state='starting',session_id=config['session_id'],silent=True,
                                updated_monotonic=time.monotonic())
                status_paths = [display_config.parent/'player_status.json',
                    Path('/dev/shm')/(display_config.parent.name+'-player-status.json')]
                for target in status_paths:
                    pending = target.with_suffix('.audio-restore.tmp')
                    pending.write_text(json.dumps(starting))
                    os.replace(pending,target)
            if run('systemctl', 'show', unit, '-p', 'LoadState', '--value') == 'not-found':
                command = ['systemd-run', '--unit='+unit]
                command += ['--property='+key+'='+value for key, value in record['properties'].items()]
                run(*command, *record['argv'])
            else:
                run('systemctl', 'start', unit)
            if run('systemctl', 'show', unit, '-p', 'ActiveState', '--value') != 'active':
                raise RuntimeError('Previous service did not restart: '+unit)
            if display_config is not None:
                deadline = time.monotonic()+45
                while True:
                    row = json.loads(status_paths[1].read_text())
                    if row['session_id'] == config['session_id'] and row.get('state') in ('menu','playing'):
                        break
                    if not service_pid(unit) or time.monotonic()>deadline:
                        raise RuntimeError('Previous display did not publish a fresh ready state: '+str(row))
                    time.sleep(.2)
            restored.append(unit)
        save('runtime_restored.json', dict(services=restored, boot=state['boot'],
             previous_program_files_modified=False, motors_commanded=False))


def trial(state):
    import numpy as np
    from pynq import Overlay, PL, allocate
    from audio_session import PcmSession
    report = dict(audio_attempted=False, audible_verified=False, phases=[],
                  original_restored=False, buffers_released=False, motors_commanded=False)
    locks, buffers = [], []
    mapped = attempted = False
    audio = reader = None
    lib = C.CDLL(state['display_library'])
    lib.display_open.argtypes = [C.POINTER(C.c_uint32)]
    lib.display_open.restype = lib.display_close.restype = C.c_int
    lib.display_park.argtypes = [C.c_uint]
    lib.display_park.restype = C.c_int
    lib.display_frames.restype = lib.display_index.restype = lib.display_status.restype = C.c_uint32
    def stopped(*_):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, stopped)
    signal.signal(signal.SIGINT, stopped)
    def scan():
        before = lib.display_frames()
        due = time.monotonic()+.3
        while lib.display_frames() == before:
            if time.monotonic() > due:
                raise RuntimeError('Candidate HDMI scan stopped')
            time.sleep(.002)
        if lib.display_status() & 0x80000ff1:
            raise RuntimeError('Candidate display DMA reported error/halt')
        return lib.display_frames()
    def phase(name, seconds, video=None):
        report['audio_attempted'] = True
        revision = audio.play(Path(state['assets'])/name, volume=state['volume'])
        beginning = time.monotonic()
        views = []
        frames = 0
        while time.monotonic()-beginning < seconds:
            view = audio.snapshot()
            if view['revision'] == revision and view['phase'] == 'error':
                raise RuntimeError('PCM playback failed: '+str(view))
            if video is not None:
                index = (lib.display_index()+1)%3
                rc = video.video_read_to(reader, buffers[index].ctypes.data, 1280, 720, 3840)
                if rc == 1:
                    buffers[index].flush()
                    if not lib.display_park(index):
                        raise RuntimeError('Video buffer did not latch')
                    frames += 1
                elif rc != 0:
                    raise RuntimeError('Uploaded video decode failed')
            scan()
            if len(views) < 50:
                views.append(view)
            if view['revision'] == revision and view['phase'] == 'completed' and view['pid'] is None:
                break
            time.sleep(.02)
        ending = audio.snapshot()
        audio.stop()
        due = time.monotonic()+3
        while audio.snapshot()['pid'] is not None:
            if time.monotonic() > due:
                raise RuntimeError('Audio did not stop before next phase')
            time.sleep(.02)
        report['phases'].append(dict(asset=name, seconds=time.monotonic()-beginning,
                                     final=ending, samples=views, video_frames=frames))
        save('trial_report.json', report)
        time.sleep(.5)
    try:
        verify(state)
        for name in ('guardianloop-pl.lock', 'tobii_display.lock'):
            handle = open('/run/lock/'+name, 'a')
            fcntl.flock(handle, fcntl.LOCK_EX|fcntl.LOCK_NB)
            locks.append(handle)
        if PL.bitfile_name != state['original']:
            raise RuntimeError('Expected original PL after previous display cleanup')
        startup = json.loads(Path('/run/guardianloop-startup/status.json').read_text())
        if startup['boot_id'] != state['boot'] or startup['pl']['used_by_current_cap'] is not False:
            raise RuntimeError('ARM-only acquisition not verified')
        if any(line.split()[0].startswith('gldma') for line in Path('/proc/modules').read_text().splitlines()):
            raise RuntimeError('DMA keeper prevents PL switching')
        for _ in range(3):
            image = allocate(shape=(720,1280,3), dtype=np.uint8)
            image[:] = (22,32,42)
            image[300:420,520:760] = (60,170,190)
            image.flush()
            buffers.append(image)
        attempted = True
        overlay = Overlay(state['candidate'])
        required = dict(axi_vdma_0=0x43000000, axi_vdma_1=0x43010000,
                        live_osd_0=0x43c00000, v_tc_0=0x43c10000, pcm_buffer_0=0x43c20000)
        if any(overlay.ip_dict.get(k,{}).get('phys_addr') != v for k,v in required.items()):
            raise RuntimeError('Candidate address map mismatch')
        mapped = True
        if not lib.display_open((C.c_uint32*3)(*[b.physical_address for b in buffers])) or not lib.display_park(0):
            raise RuntimeError('Candidate display could not start')
        first = scan()
        time.sleep(.3)
        report['scan_delta'] = (scan()-first) & 0xffffffff
        save('trial_report.json', report)
        print('CANDIDATE_HDMI_SCANNING_LOW_VOLUME_AUDIO_NEXT', flush=True)
        audio = PcmSession([state['player']])
        time.sleep(2)
        for _ in range(2 if state['speech_only'] else 1):
            phase('need_water_48k.wav', 6)
            phase('need_help_48k.wav', 6)
        if state['speech_only']:
            report['hardware_phases_finished'] = True
            return
        phase('carefree_48k.wav', 8)
        video = C.CDLL(state['decoder_library'])
        video.video_open.argtypes = [C.c_char_p,C.c_int]
        video.video_open.restype = C.c_void_p
        video.video_close.argtypes = [C.c_void_p]
        video.video_read_to.argtypes = [C.c_void_p,C.c_void_p,C.c_int,C.c_int,C.c_int]
        video.video_read_to.restype = C.c_int
        reader = video.video_open(state['video'].encode(), 2)
        if not reader:
            raise RuntimeError('Cannot open original uploaded video')
        phase('uploaded_video_audio_48k.wav', 6, video)
        report['hardware_phases_finished'] = True
    except KeyboardInterrupt:
        report['interrupted'] = True
    except Exception as error:
        report['error'] = str(error)
    finally:
        try:
            if audio:
                audio.close()
            if reader:
                video.video_close(reader)
            with (BASE/'display_restore.lock').open('a') as lock:
                fcntl.flock(lock, fcntl.LOCK_EX)
                halted = bool(lib.display_close()) if mapped else True
                report['display_halted'] = halted
                if attempted:
                    # Full reconfiguration stops DMA before releasing any CMA buffer.
                    Overlay(state['original'])
                    report['original_restored'] = PL.bitfile_name == state['original']
                    if not report['original_restored']:
                        raise RuntimeError('Original PL recovery failed; retain CMA buffers')
                for buffer in buffers:
                    buffer.freebuffer()
                report['buffers_released'] = True
        except Exception as error:
            report['recovery_error'] = str(error)
        save('trial_report.json', report)
        print(json.dumps(report), flush=True)
        if not report['buffers_released']:
            signal.signal(signal.SIGTERM, signal.SIG_IGN)
            while True:
                time.sleep(1)
        for lock in locks:
            lock.close()
        restore(state)
    if report.get('error') or report.get('recovery_error'):
        raise SystemExit(1)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('trial','restore'))
    args = parser.parse_args()
    state = json.loads((BASE/'state.json').read_text())
    if args.action == 'trial':
        trial(state)
    else:
        restore(state)

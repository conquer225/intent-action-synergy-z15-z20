"""Fail-closed admission for the audited ARM brain + HDMI eye candidate.

This module never downloads an overlay, starts/stops a service, or opens USB.
The eye session keeps its original calibration/menu code and display lock.
"""
import hashlib
import json
from pathlib import Path
import os

BRAIN_ROOT = Path('/home/xilinx/jupyter_notebooks/guardianloop_pynq')
CHANNELS = ('F3', 'F4', 'C3', 'C4', 'T7', 'T8', 'O1', 'O2')
EXPECTED_MANIFEST = '778ea2e8846c1d3985c032fe0ad2722339a90bbb782e4b4a3f98399cfc0d6705'
PRIMARY_MANIFEST = 'f26fa30b19e110ec18e800a1779a06b2e003dcf48fb1dfddc214df368f4f4b26'
EYE_BIT_SHA = '8b52892466a1b4d025c5c693a951727ae6215e57ca3e5fa0dedaa2a1d510d50f'
EYE_HWH_SHA = '5dcfe537c6793f5b18b47550f73078ab8d73500888e585037a707c8be1ebacef'
STARTUP = Path('/run/guardianloop-startup/status.json')
SERVICE = 'guardianloop-cyton.service'


def file_sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verify_release(root):
    manifest_path = root / 'release_manifest.json'
    if file_sha(manifest_path) not in (EXPECTED_MANIFEST, PRIMARY_MANIFEST):
        raise RuntimeError('Brain release is not the audited coexistence release')
    manifest = json.loads(manifest_path.read_text())
    if tuple(manifest['channels']) != CHANNELS:
        raise RuntimeError('Fixed eight-channel layout changed')
    for name, expected in manifest['files'].items():
        if Path(name).name != name or name in ('.', '..'):
            raise RuntimeError('Release file escapes brain root')
        if file_sha(root / name) != expected:
            raise RuntimeError('Brain release checksum changed: ' + name)
    return manifest


def check_arm_contract(startup, process, boot, modules, keeper_present, require_acquisition=True):
    if keeper_present or any(name.startswith('gldma') for name in modules):
        raise RuntimeError('A PL DMA owner is present; coexistence is forbidden')
    if startup.get('state') != 'ready' or startup.get('boot_id') != boot:
        raise RuntimeError('Brain self-test is not ready for this boot')
    if startup.get('pl', {}).get('used_by_current_cap') is not False:
        raise RuntimeError('Brain PL independence is not verified')
    required = {'filter_quality', 'emotion', 'fatigue', 'seed_candidate',
                'ssvep_candidate', 'mi_virtual'}
    tasks = startup.get('tasks', {})
    if not required.issubset(tasks) or any(tasks[name].get('backend') != 'arm' for name in required):
        raise RuntimeError('Every current brain task must use ARM')
    if tuple(tasks['filter_quality'].get('channels', ())) != CHANNELS:
        raise RuntimeError('Runtime channel layout does not match')
    if tasks['mi_virtual'].get('physical_control') is not False:
        raise RuntimeError('This candidate does not arbitrate physical actuators')
    if process.get('state') != 'active' or process.get('pid', 0) <= 0:
        if (not require_acquisition and (process.get('state') in (
                'inactive', 'failed', 'activating', 'deactivating') or process.get('read_race') is True)):
            return False
        raise RuntimeError('Brain acquisition must already be running')
    argv = process['argv']
    if str(BRAIN_ROOT / 'guardianloop_acquisition.py') not in argv:
        raise RuntimeError('Unrecognized acquisition entry point')
    if '--filter-backend' in argv and argv[argv.index('--filter-backend') + 1] != 'arm':
        raise RuntimeError('Brain filter is using PL')
    if any(arg.startswith('--filter-backend=') and arg != '--filter-backend=arm' for arg in argv):
        raise RuntimeError('Brain filter is using PL')
    if '--channel-map' in argv or any(arg.startswith('--channel-map=') for arg in argv):
        raise RuntimeError('Channel override is not allowed in coexistence')
    env = process['environment']
    if tuple(env.get('GL_CHANNEL_MAP', ','.join(CHANNELS)).split(',')) != CHANNELS:
        raise RuntimeError('Configured channel layout changed')
    if env.get('GL_COVARIANCE_MODEL', str(BRAIN_ROOT / 'gameemo_covariance_svm.npz')) != str(BRAIN_ROOT / 'gameemo_covariance_svm.npz'):
        raise RuntimeError('Unverified covariance model override')
    return True


def process_contract():
    import dbus
    # systemctl reads the same properties, but spawning it can stall scan threads.
    bus = dbus.SystemBus(private=True)
    try:
        manager = bus.get_object('org.freedesktop.systemd1',
                                 '/org/freedesktop/systemd1', introspect=False)
        path = manager.GetUnit(SERVICE, dbus_interface='org.freedesktop.systemd1.Manager',timeout=3)
        unit = bus.get_object('org.freedesktop.systemd1',path,introspect=False)
        status = unit.GetAll('org.freedesktop.systemd1.Unit',
                            dbus_interface='org.freedesktop.DBus.Properties',timeout=3)
        service = unit.GetAll('org.freedesktop.systemd1.Service',
                             dbus_interface='org.freedesktop.DBus.Properties',timeout=3)
        fields = dict(ActiveState=str(status['ActiveState']), MainPID=int(service['MainPID']),
                      NRestarts=int(service['NRestarts']))
    finally:
        bus.close()
    pid = int(fields['MainPID'])
    if pid <= 0:
        return {'state': fields['ActiveState'], 'pid': pid}
    proc = Path('/proc') / str(pid)
    try:
        argv = [part.decode() for part in (proc / 'cmdline').read_bytes().split(b'\0') if part]
        start_ticks = int((proc / 'stat').read_text().rsplit(')', 1)[1].split()[19])
        # Only inspect the relevant configuration keys; never export secrets.
        env = {}
        for part in (proc / 'environ').read_bytes().split(b'\0'):
            key, separator, value = part.partition(b'=')
            if separator and key in (b'GL_CHANNEL_MAP', b'GL_COVARIANCE_MODEL'):
                env[key.decode()] = value.decode()
    except (FileNotFoundError, ProcessLookupError):
        return {'state': fields['ActiveState'], 'pid': 0, 'read_race': True}
    return {'state': fields['ActiveState'], 'pid': pid,
            'start_ticks': start_ticks, 'restarts': int(fields['NRestarts']),
            'argv': argv, 'environment': env}


def verify_shared_lease(eye_root, current, boot):
    import fcntl
    lease = json.loads((Path(eye_root) / 'shared_pl.json').read_text())
    if lease['boot_id'] != boot or lease['bitfile'] != current:
        raise RuntimeError('Shared PL lease does not match this boot/overlay')
    if current != str(Path(eye_root) / 'overlay/eye_wifi.bit'):
        raise RuntimeError('Unverified shared overlay path')
    if lease['recovery'] != str(BRAIN_ROOT / 'guardianloop_pynq.bit'):
        raise RuntimeError('Unverified shared PL recovery target')
    os.kill(int(lease['owner_pid']), 0)
    with open('/run/lock/guardianloop-pl.lock', 'a') as lock:
        try:fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:return lease
    raise RuntimeError('Shared PL owner does not hold the configuration lock')


class CoexistGuard:
    def __init__(self, eye_root, original, shared=False, allow_acquisition_restart=False):
        self.eye_root = Path(eye_root)
        self.original = str(original)
        self.process = None
        self.shared = shared
        self.allow_acquisition_restart = allow_acquisition_restart
        self.boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()

    def verify(self):
        if self.shared:
            verify_shared_lease(self.eye_root, self.original, self.boot)
        elif self.original != str(BRAIN_ROOT / 'guardianloop_pynq.bit'):
            raise RuntimeError('The verified GuardianLoop overlay must be the recovery target')
        manifest = verify_release(BRAIN_ROOT)
        for name, expected in (('eye_wifi.bit', EYE_BIT_SHA), ('eye_wifi.hwh', EYE_HWH_SHA)):
            if file_sha(self.eye_root / 'overlay' / name) != expected:
                raise RuntimeError('Eye bit/HWH differs from the verified SD copy')
        self.check_runtime(require_acquisition=True)
        return {'brain_release': manifest['release_id'], 'brain_pid': self.process['pid'],
                'boot_id': self.boot, 'brain_backend': 'arm', 'pl_role': 'eye_hdmi',
                'brain_services_stopped': False, 'physical_control': False}

    @property
    def acquisition_identity(self):
        if self.process and self.process.get('state') == 'active' and self.process.get('pid', 0) > 0:
            return (self.process['pid'], self.process.get('start_ticks', 0))
        return None

    def check_runtime(self, require_acquisition=False):
        if self.shared:
            verify_shared_lease(self.eye_root, self.original, self.boot)
        process = process_contract()
        changed = self.process is not None and (
            process.get('pid'), process.get('start_ticks')) != (
            self.process.get('pid'), self.process.get('start_ticks'))
        if changed and not self.allow_acquisition_restart:
            raise RuntimeError('Brain process changed; end eye session and recheck before retry')
        startup = json.loads(STARTUP.read_text())
        modules = [line.split()[0] for line in Path('/proc/modules').read_text().splitlines()]
        running = check_arm_contract(startup, process, self.boot, modules,
            Path('/dev/guardianloop_dma_keeper').exists(),
            require_acquisition=require_acquisition or not self.allow_acquisition_restart)
        if running and changed:
            manifest = verify_release(BRAIN_ROOT)
            if startup.get('release_id') != manifest['release_id']:
                raise RuntimeError('Restarted acquisition self-test release differs')
        self.process = process
        return running


def cleanup_display(lib, overlay, mapped, buffers, original, load_original, download_attempted=False, restore=True):
    """Do not release framebuffer memory before halt or a confirmed PL reset."""
    halted = lib.display_close() if mapped else True
    if not halted:
        if overlay is None:
            raise RuntimeError('Display DMA ownership unknown; retain buffers')
        overlay.download()  # Failure raises before any freebuffer call.
    for buffer in buffers:
        buffer.freebuffer()
    if restore and (overlay is not None or download_attempted):
        load_original(original)
        print('restored_overlay=' + original, flush=True)

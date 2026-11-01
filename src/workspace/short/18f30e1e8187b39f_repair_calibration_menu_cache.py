"""Rebuild exact menu assets off-board; keep the display and acquisition stopped/running as found."""
import hashlib
import json
from pathlib import Path
import shlex
import subprocess
import sys

import run_hdmi_live as live
from stage_calibration_repair import OUT, ROOT


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    state = json.loads((ROOT/'phone_video_upload/output/hdmi_live_user_controlled_20261008/state.json').read_text())
    installation = json.loads((OUT/'installation-stage.json').read_text())
    client = live.board.upload.trial.connect('192.168.2.99')
    records = []
    try:
        with client.open_sftp() as ftp:
            for index, base in enumerate((state['remote'], '/home/xilinx/gl-media-20261007-314e8796')):
                work = OUT/'menu-assets'/str(index)
                work.mkdir(parents=True, exist_ok=True)
                eye = '/home/xilinx/brain_eye_coexist_20261005/eye'
                sources = [(base+'/system_hdmi.py', 'system_hdmi.py')]
                for name in ('core.py', 'page_policy.py'):
                    sources.append((base+'/system_runtime/guardianloop_system/'+name, 'guardianloop_system/'+name))
                sources.append((base+'/system_runtime/wheelchair_ssvep/dry_run_bridge.py', 'wheelchair_ssvep/dry_run_bridge.py'))
                for name in ('guide_render.py', 'guide.py', 'validation.py', 'selection.py'):
                    sources.append((eye+'/src/'+name, 'eye/src/'+name))
                sources.extend((('/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf', 'cjk.ttf'),
                                ('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 'latin.ttf')))
                hashes = {}
                for remote, relative in sources:
                    local = work/relative
                    local.parent.mkdir(parents=True, exist_ok=True)
                    ftp.get(remote, str(local))
                    hashes[remote] = digest(local)
                code = """import json,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from system_hdmi import UnifiedDisplay
work=Path(sys.argv[1]);cache=work/'menu-shells-portrait-live.npz'
options=dict(live=True,dimensions=(288,512),font_paths=(work/'cjk.ttf',work/'latin.ttf'))
display=UnifiedDisplay(work/'eye',**options);display.save_shell_cache(cache)
loaded=UnifiedDisplay(work/'eye',shell_cache=cache,**options)
assert all((display.shells[p]==loaded.shells[p]).all() for p in display.shells)
print(json.dumps(dict(pages=len(display.shells),exact_roundtrip=True)))
"""
                prepared = subprocess.run([sys.executable, '-c', code, str(work.resolve())],
                                          capture_output=True, text=True, check=True)
                cache = work/'menu-shells-portrait-live.npz'
                target = base+'/'+cache.name
                backup = installation['remote']+'/menu-cache-'+str(index)+'-original.npz'
                candidate = installation['remote']+'/menu-cache-'+str(index)+'-new.npz'
                old_sha = live.board.execute(client, shlex.join(['sha256sum', target]), True).split()[0]
                ftp.get(target, str(work/'original.npz'))
                if digest(work/'original.npz') != old_sha:
                    raise ValueError('Menu cache changed while copying')
                ftp.put(str(cache), candidate)
                verify = """import hashlib,json,os,pathlib,sys
base,candidate,target,backup,expected,old_sha=sys.argv[1:7]
for path,sha in json.loads(sys.argv[7]).items():
 if hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()!=sha:raise ValueError('Menu source changed')
if hashlib.sha256(pathlib.Path(candidate).read_bytes()).hexdigest()!=expected:raise ValueError('Cache transfer changed')
if hashlib.sha256(pathlib.Path(target).read_bytes()).hexdigest()!=old_sha:raise ValueError('Existing cache changed')
if pathlib.Path(backup).exists():raise ValueError('Recovery cache already exists')
sys.path.insert(0,base)
from system_hdmi import UnifiedDisplay
display=UnifiedDisplay('/home/xilinx/brain_eye_coexist_20261005/eye',live=True,dimensions=(288,512),shell_cache=candidate)
import shutil
shutil.copy2(target,backup)
os.chmod(candidate,0o644);os.replace(candidate,target)
print(json.dumps(dict(pages=len(display.shells),verified_on_board=True,hardware_opened=False)))
"""
                command = shlex.join(['env', 'OPENBLAS_NUM_THREADS=1',
                    'PYTHONPATH='+base+'/system_runtime', live.board.PYTHON, '-c', verify,
                    base, candidate, target, backup, digest(cache), old_sha, json.dumps(hashes)])
                installed = live.board.execute(client, command, True)
                row = dict(target=target, backup=backup, old_sha=old_sha, new_sha=digest(cache),
                           preparation=json.loads(prepared.stdout), validation=json.loads(installed))
                records.append(row)
                (OUT/'menu-cache-repair.json').write_text(json.dumps(records, indent=2))
                print(json.dumps(row), flush=True)
    finally:
        client.close()


if __name__ == '__main__':
    main()

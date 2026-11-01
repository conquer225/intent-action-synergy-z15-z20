"""Explicit start/stop/status/diagnose; never installs autostart or loads PL."""
import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import time
import urllib.request
from z20_compute.release import verify_release,server_command


def identity(pid,root):
    process=Path('/proc')/str(pid)
    try:
        if b'z20_compute.headless_server' not in (process/'cmdline').read_bytes():return None
        if (process/'cwd').resolve()!=root:return None
        return (process/'stat').read_text().rsplit(') ',1)[1].split()[19]
    except (OSError,IndexError):return None


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('verify','diagnose','start','status','stop'))
    parser.add_argument('--config',type=Path,default=Path(__file__).resolve().parent/'config.json')
    args=parser.parse_args();root=Path(__file__).resolve().parent
    if args.action=='verify':print(json.dumps(verify_release(root),indent=2));return
    config=json.loads(args.config.read_text(encoding='utf-8'));command=server_command(root,config)
    state_path=root/'run/process.json'
    def state():return json.loads(state_path.read_text()) if state_path.is_file() else {}
    if args.action=='diagnose':
        report=dict(integrity=verify_release(root),python=os.sys.version,platform=os.uname() if hasattr(os,'uname') else os.name,
            silent=True,actuator_control=False,autostart=False,uio={},native={})
        import numpy as np
        report['numpy']=np.__version__
        for item in Path('/sys/class/uio').glob('uio*'):
            report['uio'][item.name]=(item/'name').read_text().strip()
        if os.name=='posix':
            for path in [root/'media/libperson_dog.so',*list((root/'assets/display').glob('*.so'))]:
                try:ctypes.CDLL(str(path));report['native'][path.name]='loadable'
                except OSError as exc:report['native'][path.name]=str(exc)
        print(json.dumps(report,indent=2));return
    if args.action=='status':
        address='http://%s:%d/status.json'%(config['bind'],config['http_port'])
        print(urllib.request.urlopen(address,timeout=3).read().decode());return
    if args.action=='stop':
        value=state();pid=value.get('pid')
        if not pid:print('already stopped');return
        actual=identity(pid,root)
        if actual is None:print('recorded process no longer owns this runtime');return
        if actual!=value.get('identity'):raise RuntimeError('PID was reused; refusing to signal it')
        os.kill(pid,signal.SIGTERM)
        deadline=time.monotonic()+15
        while identity(pid,root) is not None and time.monotonic()<deadline:time.sleep(.1)
        if identity(pid,root) is not None:raise RuntimeError('clean shutdown timed out; inspect log')
        state_path.unlink();print('stopped');return
    verify_release(root)
    if os.name!='posix' or not Path('/proc/self').exists():raise RuntimeError('board launcher requires Linux /proc')
    old=state()
    if old.get('pid') and identity(old['pid'],root) is not None:raise RuntimeError('runtime already running')
    (root/'run').mkdir(exist_ok=True)
    with (root/'run/service.log').open('ab') as log:
        process=subprocess.Popen(command,cwd=str(root),stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
    fingerprint=identity(process.pid,root)
    if fingerprint is None:
        process.terminate();process.wait(5);raise RuntimeError('server failed before process ownership could be recorded')
    state_path.write_text(json.dumps(dict(pid=process.pid,identity=fingerprint,command=command),indent=2))
    deadline=time.monotonic()+30
    while time.monotonic()<deadline:
        if process.poll() is not None:raise RuntimeError('server exited; inspect run/service.log')
        try:
            value=json.load(urllib.request.urlopen('http://%s:%d/status.json'%(config['bind'],config['http_port']),timeout=1))
            if value['pid']==process.pid:print(json.dumps(dict(started=True,pid=process.pid)));return
        except (OSError,ValueError):pass
        time.sleep(.2)
    process.terminate();process.wait(15);raise RuntimeError('server readiness timed out; inspect log')


if __name__=='__main__':main()

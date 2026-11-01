"""Read-only board evidence for repeated calibration, without raw EEG or keys."""
import json
from pathlib import Path
import shlex

import run_hdmi_live as live


OUT = Path(__file__).resolve().parent / 'output/calibration_recovery_20261008'


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    client = live.board.upload.trial.connect('192.168.2.99')
    try:
        commands = {
            'services': ['systemctl', 'show', 'guardianloop-cyton.service',
                         'guardianloop-web.service', '-p', 'MainPID', '-p', 'ActiveState',
                         '-p', 'NRestarts', '-p', 'ExecMainStartTimestamp', '-p', 'Result'],
            'acquisition_log': ['journalctl', '-u', 'guardianloop-cyton.service',
                                '-n', '450', '--no-pager', '-o', 'short-iso'],
            'kernel_log': ['journalctl', '-k', '-n', '450', '--no-pager', '-o', 'short-iso'],
            'network': ['ip', '-br', 'addr'],
            'load': ['ps', '-eo', 'pid,ppid,psr,pcpu,pmem,comm', '--sort=-pcpu'],
            'usb': ['lsusb', '-t'],
        }
        evidence = {name: live.board.execute(client, shlex.join(cmd), name.endswith('_log'))
                    for name, cmd in commands.items()}
        code = '''import json,urllib.request
from pathlib import Path
for port,path in ((9102,'/api/status'),(9105,'/api/ssvep-hdmi')):
 try:
  with urllib.request.urlopen('http://127.0.0.1:%s%s'%(port,path),timeout=3) as r: row=json.load(r)
  if port==9102:
   f=row.get('fatigue',{}); t=row.get('telemetry',{})
   print(json.dumps(dict(port=port,stale=row.get('stale'),fatigue={k:v for k,v in f.items() if k not in ('sqi','raw_interference','emotion')},runtime=t.get('runtime'),status_keys=list(row))))
  else:
   print(json.dumps({k:v for k,v in row.items() if k in ('state','reason','control_enabled','policy','updated_at')}))
 except (OSError,ValueError) as e: print(json.dumps(dict(port=port,error=str(e))))
for name in ('/run/guardianloop/status.json','/run/guardianloop/telemetry.json'):
 try:
  row=json.loads(Path(name).read_text()); print(json.dumps(dict(file=name,runtime=row.get('runtime'),counts={k:row.get(k) for k in ('updated_at','packets_seen','malformed_bytes','sequence_gaps','dropped_packets')})))
 except (OSError,ValueError) as e: print(json.dumps(dict(file=name,error=str(e))))
'''
        evidence['status'] = live.board.execute(client, shlex.join([live.board.PYTHON, '-c', code]))
        code = '''import json,subprocess
from collections import Counter
from pathlib import Path
log=subprocess.check_output(['journalctl','-u','guardianloop-cyton.service','--since','2026-10-08 13:48:50','--no-pager','-o','cat'],text=True)
counts=Counter(); windows=[]; recent=[]
for line in log.splitlines():
 if 'PRIMARY_STREAM_RESET' in line: counts['resets']+=1
 if 'CYTON_WAITING' in line: counts['wait_probes']+=1
 if line.startswith('CYTON_WINDOW_RESULT: '):
  r=json.loads(line.split(': ',1)[1]); windows.append({k:r.get(k) for k in ('window','state','reason','calibration_current','packets_seen','malformed_bytes','sequence_gaps')})
 if 'CYTON_READER_FAILURE' in line: recent.append(line)
print(json.dumps(dict(events=counts,windows=windows[-18:],reader_failures=recent[-8:])))
pid=subprocess.check_output(['systemctl','show','guardianloop-cyton.service','-p','MainPID','--value'],text=True).strip()
args=[p.decode() for p in Path('/proc/'+pid+'/cmdline').read_bytes().split(b'\\0') if p]
print(json.dumps(dict(argv=args)))
env=Path('/proc/'+pid+'/environ').read_bytes().split(b'\\0')
print(json.dumps(dict(env=[p.decode() for p in env if p.startswith((b'GL_',b'OPENBLAS_',b'OMP_',b'MKL_'))])))
port='/dev/serial/by-id/usb-FTDI_FT231X_USB_UART_D309LDXY-if00-port0'
print(json.dumps(dict(serial_exists=Path(port).exists(),serial_target=str(Path(port).resolve()))))
p=subprocess.run(['fuser','-v',port],capture_output=True,text=True)
print(json.dumps(dict(serial_users=p.stdout+p.stderr,returncode=p.returncode)))
for p in Path('/proc/'+pid+'/fd').iterdir():
 try:
  target=str(p.resolve())
  if '/dev/tty' in target: print(json.dumps(dict(open_serial_fd=p.name,target=target)))
 except OSError: pass
print(subprocess.check_output(['systemctl','list-units','--all','--no-pager','--plain','--no-legend','gl-phone-*','guardianloop-ap*','guardianloop-dhcp*'],text=True))
'''
        evidence['details'] = live.board.execute(client, shlex.join([live.board.PYTHON, '-c', code]), True)
        import time
        target = OUT / ('audit-' + time.strftime('%H%M%S') + '.json')
        target.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding='utf-8')
        for name in ('services', 'network', 'usb', 'status', 'details'):
            print(name + '\n' + evidence[name])
        tokens = ('PRIMARY_STREAM_RESET', 'CYTON_READER_FAILURE', 'CYTON_WAITING',
                  'CYTON_STREAM_STARTED', 'PROCESSING_BACKLOG', 'Traceback', 'Stopped', 'Started')
        rows = [line for line in evidence['acquisition_log'].splitlines() if any(t in line for t in tokens)]
        print('acquisition events\n' + '\n'.join(rows[-65:]))
        rows = [line for line in evidence['kernel_log'].splitlines()
                if any(t in line.lower() for t in ('usb', 'ftdi', 'over-current', 'reset', 'oom', 'killed'))]
        print('kernel events\n' + '\n'.join(rows[-65:]))
        print('top load\n' + '\n'.join(evidence['load'].splitlines()[:16]))
        print('EVIDENCE_SAVED', target)
    finally:
        client.close()


if __name__ == '__main__':
    main()

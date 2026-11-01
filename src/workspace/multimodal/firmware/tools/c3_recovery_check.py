"""Reset only C3 while observing disabled S3; record loss and recovery."""
from pathlib import Path
import json
import re
import subprocess
import time
import serial
from device_telemetry import hand_telemetry

root = Path(__file__).resolve().parents[1]
device = serial.Serial()
device.port='COM27'; device.baudrate=115200; device.timeout=0.1
device.dtr=False; device.rts=False; device.open()
device.write(b'estop\nstream status\nlink\n')
started=time.monotonic()
reboot=None
samples=[]
links=[]
next_request=5
hand_output_acknowledged=[]
with (root/'records/c3_recovery_s3_20261011.log').open('w',encoding='utf-8') as log:
    while time.monotonic()-started<25:
        elapsed=time.monotonic()-started
        if reboot is None and elapsed>=3:
            exe='C:/Users/conquer/AppData/Local/Arduino15/packages/esp32/tools/esptool_py/5.3.1/esptool.exe'
            with (root/'records/c3_recovery_reset_20261011.log').open('w') as reset_log:
                reboot=subprocess.Popen([exe,'--chip','esp32c3','--port','COM20','run'],stdout=reset_log,stderr=subprocess.STDOUT)
        line=device.readline().decode(errors='replace').strip()
        if not line: continue
        log.write(f'{elapsed:.3f} {line}\n')
        if line.startswith('# wifi:'):
            fields=dict(re.findall(r'(\w+):([^,\s]+)',line));fields['elapsed']=round(elapsed,3);samples.append(fields)
        if line.startswith('LINK,'): links.append(line)
        if line.startswith('TELEM_V3,'):
            parsed=hand_telemetry(line)
            if parsed: hand_output_acknowledged.append(parsed['output_acknowledged'])
        if elapsed>=next_request:
            device.write(b'link\n'); next_request+=5
device.close()
result={'reset_exit_code':reboot.wait(timeout=10),'samples':len(samples),
        'bridge_loss_seen':any(s.get('bridge')=='0' for s in samples),
        'recovered':bool(samples and samples[-1].get('bridge')=='1'),
        'pendulum_stayed_off':bool(samples and all(s.get('pend_enabled')=='0' for s in samples)),
        'hand_output_acknowledged_seen':any(hand_output_acknowledged),
        'hand_samples':len(hand_output_acknowledged),
        'last':samples[-1] if samples else None, 'links':links}
(root/'records/c3_recovery_summary_20261011.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in result.items() if k!='links'}),flush=True)
if not (result['reset_exit_code']==0 and result['bridge_loss_seen'] and result['recovered'] and result['pendulum_stayed_off'] and result['hand_samples'] and not result['hand_output_acknowledged_seen']):
    raise SystemExit('C3 recovery check failed; inspect raw logs')

"""One authorised leaf-device reset; no service, hub, eye or PL operation."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time


ROOT = Path(__file__).resolve().parent
IDENTITY = Path('/dev/serial/by-id/usb-FTDI_FT231X_USB_UART_D309LDXY-if00-port0')


def main():
    plan = json.loads((ROOT/'reset-plan.json').read_text())
    if Path('/proc/sys/kernel/random/boot_id').read_text().strip() != plan['boot']:
        raise RuntimeError('Boot changed; refuse old USB reset plan')
    tty = IDENTITY.resolve(strict=True)
    usb = next(p for p in (Path('/sys/class/tty')/tty.name/'device').resolve().parents
               if (p/'idVendor').is_file())
    fields = {k:(usb/k).read_text().strip() for k in
              ('idVendor','idProduct','serial','busnum','devnum')}
    if fields != plan['identity'] or str(usb) != plan['sysfs']:
        raise RuntimeError('Receiver identity/node changed before reset')
    if (fields['idVendor'],fields['idProduct'],fields['serial']) != ('0403','6015','D309LDXY'):
        raise RuntimeError('Not the authorised receiver')
    # O_EXCL prevents a second invocation after timeout or an ambiguous result.
    with (ROOT/'reset-attempted.json').open('x') as record:
        json.dump(dict(identity=fields,monotonic=time.monotonic(),pid=os.getpid()),record)
        record.flush()
        os.fsync(record.fileno())
    node = '/dev/bus/usb/%03d/%03d' % (int(fields['busnum']),int(fields['devnum']))
    print('ONE_LEAF_RESET_BEGIN '+node,flush=True)
    started = time.monotonic()
    report = dict(node=node,identity=fields,attempts=1,hub_reset=False,
                  eye_reset=False,PL_reload=False,services_restarted=False)
    try:
        fd = os.open(node,os.O_WRONLY)
        try:
            fcntl.ioctl(fd,0x5514,0)  # Installed Linux header: _IO('U',20).
        finally:
            os.close(fd)
        report['reset_returned_success'] = True
    except OSError as error:
        report.update(reset_returned_success=False,error=str(error),errno=error.errno)
    report['elapsed_seconds'] = time.monotonic()-started
    checkpoint = Path('/run/guardianloop/calibration-session.json')
    report['calibration_sha_after'] = hashlib.sha256(checkpoint.read_bytes()).hexdigest() if checkpoint.exists() else None
    report['calibration_sha_before'] = plan['calibration_sha_before']
    report['service'] = subprocess.check_output(['systemctl','show','guardianloop-cyton.service',
        '-p','MainPID','-p','ActiveState'],text=True).strip()
    (ROOT/'reset-result.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report),flush=True)


if __name__ == '__main__':
    main()

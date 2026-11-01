"""Temporary UART-directed kernel boot; never save U-Boot environment."""
from pathlib import Path
import serial,time,json
o=Path('build/navigator'); log=o/'temporary_boot_resume.log'
p=serial.Serial('COM15',115200,timeout=.1,write_timeout=2)
f=log.open('wb'); full=bytearray()
def drain(seconds):
 end=time.monotonic()+seconds
 while time.monotonic()<end:
  b=p.read(32768)
  if b:f.write(b);f.flush();full.extend(b)
def command(s):
 for b in (s+'\r').encode():p.write(bytes([b]));time.sleep(.003)
try:
 p.reset_input_buffer();command('sync');drain(.5);command('reboot')
 deadline=time.monotonic()+35;found=False
 while time.monotonic()<deadline:
  drain(.15)
  if b'Hit any key to stop autoboot' in full:
   p.write(b' ');drain(.5);found=True;break
 if not found:raise RuntimeError('U-Boot countdown not seen; no boot parameters changed')
 commands=[
  'fatload mmc 0:1 0x03000000 navigator-bringup/zImage',
  'fatload mmc 0:1 0x02a00000 navigator-bringup/system.dtb',
  'mw.l 0xf8000008 0xdf0d',
  'mw.l 0xf8000240 0xf',
  'setenv bootargs earlycon console=ttyPS0,115200 cma=50M root=/dev/mmcblk1p1 rw rootwait clk_ignore_unused uio_pdrv_genirq.of_id=generic-uio',
  'bootz 0x03000000 - 0x02a00000']
 for s in commands:
  command(s);drain(1)
 drain(55)
 # The original system normally auto-logs root in on UART.
 command('echo NAVIGATOR_TEMP_BOOT; cat /proc/cmdline; ls /sys/class/uio');drain(2)
 command('ifconfig eth0 192.168.1.20 netmask 255.255.255.0 up');drain(1)
 print(json.dumps(dict(countdown_seen=found,kernel_panic=b'Kernel panic' in full,
  temporary_marker=b'NAVIGATOR_TEMP_BOOT' in full,uio=b'uio0' in full,log=str(log))))
finally:p.close();f.close()

"""Compile packaged sources. Does not upload, enumerate ports or enable devices."""
import argparse,json,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
TARGETS=[('s3','esp32:esp32:esp32s3:CDCOnBoot=cdc,USBMode=hwcdc','esp32/MultiControlS3'),
         ('c3','esp32:esp32:esp32c3:CDCOnBoot=cdc','esp32c3/PendulumBridgeC3'),
         ('nano','arduino:avr:nano:cpu=atmega328old','hand_nano/hand_controller')]
def main():
    p=argparse.ArgumentParser();p.add_argument('--arduino-cli',default='arduino-cli');p.add_argument('--config');p.add_argument('--keil');a=p.parse_args()
    for name,fqbn,source in TARGETS:
        output=ROOT/'build/firmware'/name;output.mkdir(parents=True,exist_ok=True)
        command=[a.arduino_cli,'compile','--fqbn',fqbn,'--output-dir',str(output)]
        if a.config:command+=['--config-file',a.config]
        if name=='s3':command+=['--build-property','compiler.cpp.extra_flags=-DMULTICONTROL_AUTO_START=0']
        command+=['--libraries',str(ROOT/'firmware/libraries'),str(ROOT/'firmware'/source)]
        with (output/'compile.log').open('w',encoding='utf8') as log:r=subprocess.run(command,stdout=log,stderr=subprocess.STDOUT)
        if r.returncode:raise RuntimeError('build failed: '+name+'; read '+str(output/'compile.log'))
        print('built='+name)
    if a.keil:
        log=ROOT/'build/firmware/stm32_compile.log'
        r=subprocess.run([a.keil,'-b',str(ROOT/'firmware/stm32/Project.uvprojx'),'-j0','-o',str(log)])
        if not log.exists() or '0 Error(s)' not in log.read_text(errors='replace'):raise RuntimeError('STM32 build failed; read '+str(log))
        print('built=stm32')
if __name__=='__main__':main()

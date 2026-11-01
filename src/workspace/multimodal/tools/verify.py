"""Reproduce checks in this directory; failures propagate to the caller."""
import argparse,ast,json,os,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def run(command,log):
    log.parent.mkdir(parents=True,exist_ok=True)
    with log.open('w',encoding='utf8') as output:r=subprocess.run(command,cwd=ROOT,stdout=output,stderr=subprocess.STDOUT)
    if r.returncode:raise RuntimeError('check failed: '+str(log))
    return log.read_text(errors='replace')
def main():
    p=argparse.ArgumentParser();p.add_argument('--firmware-tests',action='store_true');p.add_argument('--rtl',action='store_true');p.add_argument('--vcvars');a=p.parse_args()
    for file in (ROOT/'intent_one').glob('*.py'):ast.parse(file.read_text(encoding='utf8'),feature_version=(3,8))
    run([sys.executable,'-m','unittest','discover','-s','tests','-v'],ROOT/'report/python_tests.log')
    run([sys.executable,'-m','intent_one','preflight'],ROOT/'report/preflight.log')
    if a.firmware_tests:
        os.environ['JSON_INCLUDE']=str(ROOT/'firmware/libraries/ArduinoJson/src')
        if a.vcvars:os.environ['VCVARS64']=a.vcvars
        # The retained boot fixtures assume an already-configured network.
        # Stub credentials exist only for host tests, never for firmware builds.
        test_wifi=ROOT/'firmware/esp32/MultiControlS3/WifiConfig.h';created=False
        try:
            if not test_wifi.exists():
                test_wifi.write_text('#pragma once\nconstexpr char WIFI_SSID[]="Test-Control";\nconstexpr char WIFI_PASSWORD[]="test-only-12345";\nconstexpr char CONTROLLER_DEVICE_NAME[]="test-s3";\n',encoding='utf8');created=True
            for name in ('run_tests','run_multimodal_tests','run_bridge_tests','run_c3_tests','run_multicontrol_tests','run_mpu_tests','run_boot_tests'):
                run(['cmd','/d','/c',str(ROOT/'firmware/tests'/(name+'.cmd'))],ROOT/'report'/(name+'.log'))
        finally:
            if created:test_wifi.unlink()
        run([sys.executable,'-m','unittest','discover','-s','firmware/tests','-p','test_pc_client.py','-v'],ROOT/'report/pc_client_tests.log')
    if a.rtl:
        tool=[sys.executable,str(ROOT/'tools/vivado_tool.py')]
        run(tool+['xvlog','-sv','hardware/signal_core.sv','hardware/tb_signal.sv','hardware/tb_signal_axi.sv','hardware/stimulus_core.sv','hardware/tb_stimulus.sv','hardware/key_inputs.v','hardware/tb_keys.sv'],ROOT/'report/xvlog.log')
        for top in ('tb_signal','tb_signal_axi','tb_stimulus','tb_keys'):
            run(tool+['xelab',top,'-s',top],ROOT/'report'/(top+'_elaborate.log'))
            text=run(tool+['xsim',top,'-runall'],ROOT/'report'/(top+'.log'))
            if ' PASS' not in text or 'Fatal:' in text:raise RuntimeError('simulation did not pass: '+top)
    print(json.dumps({'python':'passed','release':'verified','firmware_tests':a.firmware_tests,'rtl':a.rtl}))
if __name__=='__main__':main()

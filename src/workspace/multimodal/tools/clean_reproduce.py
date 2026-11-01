"""Verify a delivered ZIP outside the maintained checkout. Retain logs for review."""
import argparse,hashlib,json,subprocess,sys,tempfile,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def run(command,cwd,output):
    with output.open('w',encoding='utf8') as log:result=subprocess.run(command,cwd=cwd,stdout=log,stderr=subprocess.STDOUT)
    if result.returncode:raise RuntimeError('clean reproduction failed: '+str(output))
def main():
    p=argparse.ArgumentParser();p.add_argument('archive',type=Path);p.add_argument('--vcvars',required=True);p.add_argument('--fpga',action='store_true');p.add_argument('--arduino-cli');p.add_argument('--arduino-config');p.add_argument('--keil');a=p.parse_args()
    temp_root=Path(tempfile.gettempdir()).resolve();workspace=Path(tempfile.mkdtemp(prefix='intent-one-clean-')).resolve()
    if workspace.parent!=temp_root or not workspace.name.startswith('intent-one-clean-'):raise RuntimeError('unexpected clean workspace')
    report=ROOT/'report/clean';report.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(a.archive) as archive:
        if archive.testzip():raise RuntimeError('archive CRC mismatch')
        for name in archive.namelist():
            target=(workspace/name).resolve()
            if workspace not in target.parents or not name.startswith('intent_one/') or '\\' in name:raise RuntimeError('archive member escapes workspace')
        archive.extractall(workspace)
    root=workspace/'intent_one'
    summary={'workspace':str(root),'archive_sha256':hashlib.sha256(a.archive.read_bytes()).hexdigest(),'checks':{}}
    (report/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf8')
    run([sys.executable,'tools/verify.py','--firmware-tests','--rtl','--vcvars',a.vcvars],root,report/'tests.log');summary['checks']['software_firmware_rtl']='passed'
    if a.arduino_cli:
        command=[sys.executable,'tools/build_firmware.py','--arduino-cli',a.arduino_cli]
        if a.arduino_config:command+=['--config',a.arduino_config]
        if a.keil:command+=['--keil',a.keil]
        run(command,root,report/'firmware_build.log');summary['checks']['firmware_build']='passed_with_template_network_configuration'
    if a.fpga:
        run([sys.executable,'tools/vivado_tool.py','vivado','-mode','batch','-source','hardware/create.tcl','-log','build/vivado.log','-journal','build/vivado.jou'],root,report/'fpga_build.log')
        for name in ('timing','utilization','cdc'):
            (report/(name+'.rpt')).write_bytes((root/'build'/(name+'.rpt')).read_bytes())
        if 'All user specified timing constraints are met.' not in (root/'build/timing.rpt').read_text():raise RuntimeError('clean FPGA timing failed')
        summary['checks']['fpga_build']='passed'
    (report/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf8');print(json.dumps(summary))
if __name__=='__main__':main()

"""Reconstruct HDMI/audio + vision in an isolated Vivado project, preserving ABI."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from build_hls import environment

HERE=Path(__file__).resolve().parent
PROJECT=HERE.parents[1]
BASE=HERE.parent/'guardianloop_team_20261017_03/projects/codex_project/z15_hdmi_audio'
sys.path.insert(0, str(HERE.parent/'z20_compute'))
from tool_environment import prepare


def run(root,script,out,env,name):
    executable, prepared = prepare(root)
    # Keep the corrected tool runtime; only carry the caller's build inputs.
    prepared.update({key: value for key, value in env.items() if key.startswith('GL_')})
    with (out/(name+'.txt')).open('w',encoding='utf-8') as log:
        result=subprocess.run([str(executable),'-mode','batch',
            '-nojournal','-source',script.as_posix()],cwd=out,env=prepared,stdout=log,stderr=subprocess.STDOUT)
    if result.returncode:
        print((out/(name+'.txt')).read_text(encoding='utf-8',errors='replace')[-4000:])
        raise RuntimeError(name+' failed')


def record_success(out):
    paths=['candidate/guardianloop_display_audio.bit','candidate/guardianloop_display_audio.hwh',
           'timing.rpt','cdc.rpt','methodology.rpt','drc.rpt','io.rpt','utilization.rpt']
    files={name:hashlib.sha256((out/name).read_bytes()).hexdigest() for name in paths}
    result=dict(passed=True,scope='Original project setup/hold/CDC/methodology/DRC gates before bit generation',
                files=files,tool='Vivado 2023.1',part='xc7z015clg485-2',board_loaded=False)
    (out/'quality.json').write_text(json.dumps(result,indent=2),encoding='utf-8')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--vivado',type=Path,default=Path('D:/vivado/Vivado/2023.1'))
    p.add_argument('--hls-output',type=Path,default=PROJECT/'local/vision_hls_20261019')
    p.add_argument('--vendor',type=Path,default=Path('E:/cankao/2_Embedded_Vitis/XC7Z015/XC7Z015/26_ov5640_hdmi/ip_repo'))
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    ip=(a.hls_output/'vision_hls/solution/impl/ip').resolve()
    if not (ip/'component.xml').exists():raise RuntimeError('HLS IP export is required')
    for name in ('legacy_contract.tcl','pins.xdc'):shutil.copy2(BASE/'output/full_11'/name,out/name)
    for name in ('key_inputs.v','keys.xdc'):shutil.copy2(PROJECT/'multimodal/hardware'/name,HERE/'hardware'/name)
    serializer=a.vendor/'DVI_TX/ip/src/serializer_10_to_1.v'
    if not serializer.exists():raise RuntimeError('Vendor serializer missing')
    wrapper=out/'create_vision.tcl'
    wrapper.write_text('source {'+(HERE/'hardware/source_retry.tcl').as_posix()+'}\nset_param general.maxThreads 1\nencoding system utf-8\nload_feature ipintegrator\nset argc 4\nset argv [list {'+out.as_posix()+'} {'+BASE.as_posix()+'} {'+
        a.vendor.as_posix()+'} {'+serializer.as_posix()+'}]\nsource {'+(BASE/'create_display.tcl').as_posix()+
        '}\nsource {'+(HERE/'hardware/add_vision.tcl').as_posix()+'}\n',encoding='utf-8')
    env=environment(a.vivado)
    env.update(GL_VISION_SOURCE=HERE.as_posix(),GL_VISION_BD_OUTPUT=out.as_posix(),
               GL_VISION_HLS_IP=ip.as_posix(),GL_VISION_VENDOR=a.vendor.as_posix())
    run(a.vivado,wrapper,out,env,'create-console')
    # Reuse the existing full setup/hold/CDC/DRC gates before bit generation.
    implementation=out/'implement_vision.tcl'
    implementation.write_text('source {'+(HERE/'hardware/source_retry.tcl').as_posix()+'}\nset_param general.maxThreads 1\nset_param synth.maxThreads 1\nset argc 1\nset argv [list {'+out.as_posix()+
        '}]\nsource {'+(BASE/'implement_display.tcl').as_posix()+'}\n',encoding='utf-8')
    run(a.vivado,implementation,out,env,'implementation-console')
    record_success(out)
    print('Built candidate; board has not been programmed:',out)


if __name__=='__main__':main()

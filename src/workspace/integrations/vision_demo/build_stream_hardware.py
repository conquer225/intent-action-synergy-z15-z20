"""Build autonomous camera-ring + inline pixel-filter hardware behind all gates."""
import argparse,hashlib,json,shutil,re
from pathlib import Path
from build_hls import environment
from build_hardware import run,record_success,BASE,HERE,PROJECT
def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    root=Path('D:/vivado/Vivado/2023.1')
    vendor=Path('E:/cankao/2_Embedded_Vitis/XC7Z015/XC7Z015/26_ov5640_hdmi/ip_repo')
    for n in ('legacy_contract.tcl','pins.xdc'):shutil.copy2(BASE/'output/full_11'/n,out/n)
    for n in ('key_inputs.v','keys.xdc'):shutil.copy2(PROJECT/'multimodal/hardware'/n,HERE/'hardware'/n)
    env=environment(root);env.update(GL_VISION_SOURCE=HERE.as_posix(),GL_VISION_BD_OUTPUT=out.as_posix())
    wrapper=out/'create_stream.tcl'
    wrapper.write_text('source {'+(HERE/'hardware/source_retry.tcl').as_posix()+'}\nset_param general.maxThreads 1\nencoding system utf-8\nload_feature ipintegrator\nset argc 4\nset argv [list {'+out.as_posix()+'} {'+BASE.as_posix()+'} {'+vendor.as_posix()+'} {'+(vendor/'DVI_TX/ip/src/serializer_10_to_1.v').as_posix()+'}]\nsource {'+(BASE/'create_display.tcl').as_posix()+'}\nsource {'+(HERE/'hardware/add_stream.tcl').as_posix()+'}\n',encoding='utf-8')
    # Vivado's feature loader is named load_feature on this installed build.
    run(root,wrapper,out,env,'create-console')
    script=out/'implement_stream.tcl'
    script.write_text('source {'+(HERE/'hardware/source_retry.tcl').as_posix()+'}\nset_param general.maxThreads 1\nset_param synth.maxThreads 1\nset argc 1\nset argv [list {'+out.as_posix()+'}]\nsource {'+(BASE/'implement_display.tcl').as_posix()+'}\n',encoding='utf-8')
    run(root,script,out,env,'implementation-console')
    timing=(out/'timing.rpt').read_text(encoding='utf-8')
    for check in ('no_clock','unconstrained_internal_endpoints','multiple_clock','loops','latch_loops'):
        found=re.search(r'checking '+check+r' \((\d+)\)',timing)
        if not found or int(found[1]):raise RuntimeError('Incomplete timing constraints: '+check)
    record_success(out)
    quality=json.loads((out/'quality.json').read_text(encoding='utf-8'));quality['architecture']='native_stream'
    quality['source_hashes']={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (HERE/'hardware').glob('vision_stream*')}
    (out/'quality.json').write_text(json.dumps(quality,indent=2),encoding='utf-8')
if __name__=='__main__':main()

"""Resume a prepared combined project through its original complete timing gates."""
import argparse
from pathlib import Path
from build_hls import environment
from build_hardware import run,HERE,BASE,record_success

def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True)
    p.add_argument('--vivado',type=Path,default=Path('D:/vivado/Vivado/2023.1'))
    a=p.parse_args();out=a.output.resolve()
    if not (out/'combined_bd.tcl').is_file():raise RuntimeError('Validated combined BD is required')
    script=out/'resume_project.tcl'
    script.write_text('source {'+(HERE/'hardware/source_retry.tcl').as_posix()+'}\nset_param general.maxThreads 1\nset_param synth.maxThreads 1\nopen_project {'+(out/'project/hdmi_audio.xpr').as_posix()+'}\nif {[get_property PROGRESS [get_runs synth_1]] ne "100%"} {reset_runs synth_1}\nclose_project\nset argc 1\nset argv [list {'+out.as_posix()+'}]\nsource {'+(BASE/'implement_display.tcl').as_posix()+'}\n')
    run(a.vivado,script,out,environment(a.vivado),'resume-project-console')
    record_success(out)
    print('Gated combined candidate built; not loaded:',out)
if __name__=='__main__':main()

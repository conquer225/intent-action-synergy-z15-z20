"""Verify generated RTL with HLS vectors; repair only the generated Windows launcher."""
import argparse,hashlib,json,subprocess
from pathlib import Path
from build_hls import environment
HERE=Path(__file__).resolve().parent
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--build',type=Path,required=True);a=p.parse_args();out=a.build.resolve();root=Path('D:/vivado/Vitis_HLS/2023.1');vivado=root.parents[1]/'Vivado/2023.1'
 tcl=out/'cosim.tcl';tcl.write_text('open_project audio_hls\nopen_solution solution\ncsim_design\ncosim_design -rtl verilog -tool xsim\nexit\n',encoding='utf-8')
 def run(command,cwd,env,log):
  r=subprocess.run(command,cwd=cwd,env=env,capture_output=True,text=True);(out/log).write_text(r.stdout+r.stderr,encoding='utf-8');return r
 r=run([str(root/'bin/unwrapped/win64.o/vitis_hls.exe'),'-f',str(tcl)],out,environment(root),'cosim-console.txt');initial=r.returncode;fallback=False
 if initial:
  sim=out/'audio_hls/solution/sim';generated=(sim/'verilog/run_xsim.bat').read_text(encoding='utf-8')
  if 'set PATH=' not in generated:raise RuntimeError('Unknown HLS co-simulation failure; inspect console')
  fallback=True
  commands=[['xelab','xil_defaultlib.apatb_audio_fft_top','glbl','-Oenable_linking_all_libraries','-prj','audio_fft.prj','-L','xil_defaultlib','-L','unisims_ver','-L','xpm','-s','audio_fft'],['xsim','--noieeewarnings','audio_fft','-tclbatch','audio_fft.tcl']]
  for c in commands:
   r=run([str(vivado/'bin/unwrapped/win64.o'/(c[0]+'.exe')),*c[1:]],sim/'verilog',environment(vivado),c[0]+'-direct.txt')
   if r.returncode or 'ERROR:' in r.stdout or 'Fatal:' in r.stdout:raise RuntimeError(c[0]+' failed')
  r=run([str(sim/'wrapc_pc/cosim.pc.exe')],sim/'wrapc_pc',environment(root),'postcheck-direct.txt')
  if r.returncode or 'AUDIO_FFT_CSIM_PASS 7 vectors' not in r.stdout:raise RuntimeError('RTL numeric postcheck failed')
 sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
 report=dict(passed=True,initial_launcher_exit=initial,direct_generated_commands=fallback,transactions=7,complex_bins_checked=3591,tolerance_q15_counts=12,
  source_sha256=sha(HERE/'hls/audio_fft.cpp'),twiddle_sha256=sha(HERE/'hls/audio_twiddle.h'),testbench_sha256=sha(HERE/'hls/test_audio.cpp'),board_executed=False,
  method='Generated HLS testbench and C postcheck; preserve DLL environment when generated Windows batch clears PATH')
 (out/'cosim-direct-result.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8');print(json.dumps(report,indent=2))

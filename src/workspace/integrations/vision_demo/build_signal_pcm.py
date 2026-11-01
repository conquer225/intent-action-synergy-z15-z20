import argparse,hashlib,json,subprocess
from pathlib import Path
from elf_compat import validate_arm_runtime
HERE=Path(__file__).resolve().parent
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,default=HERE/'build/signal_pcm');a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
 src=HERE/'native/signal_pcm.c';binary=a.output/'signal_pcm';gcc='D:/vivado/Vitis/2023.1/gnu/aarch32/nt/gcc-arm-linux-gnueabi/bin/arm-linux-gnueabihf-gcc.exe'
 r=subprocess.run([gcc,'-std=c11','-O2','-Wall','-Wextra','-Werror','-mcpu=cortex-a9','-mfpu=vfpv3','-mfloat-abi=hard',str(src),'-o',str(binary)],capture_output=True,text=True)
 (a.output/'compiler.txt').write_text(r.stdout+r.stderr,encoding='utf-8')
 sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
 compatible=False;error=None
 if r.returncode==0:
  try:validate_arm_runtime(binary.read_bytes());compatible=True
  except ValueError as exc:error=str(exc)
 report=dict(passed=r.returncode==0 and compatible,source_sha256=sha(src),binary_sha256=sha(binary) if r.returncode==0 else None,board_executed=False,glibc_compatible=compatible,error=error)
 (a.output/'result.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8');print(json.dumps(report));raise SystemExit(0 if report['passed'] else 1)

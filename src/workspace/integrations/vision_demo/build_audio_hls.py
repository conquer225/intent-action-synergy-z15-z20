"""Run the installed HLS executable with explicit runtime paths, without editing it."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

HERE=Path(__file__).resolve().parent


def environment(root):
    env=os.environ.copy()
    # The task shell omits these standard Windows variables. Vivado's child
    # launcher otherwise exits silently as an unsupported architecture.
    env.setdefault('PROCESSOR_ARCHITECTURE','AMD64')
    env.setdefault('OS','Windows_NT')
    env.setdefault('NUMBER_OF_PROCESSORS',str(os.cpu_count() or 1))
    # Windows C runtimes do not accept the POSIX C.UTF-8 inherited from the
    # agent shell; Tcl filesystem calls can then fail with EILSEQ.
    for key in ('LANG','LC_ALL','LC_CTYPE'):env[key]='C'
    dirs=[root/'lib/win64.o',root/'bin',root/'bin/unwrapped/win64.o']
    dirs += [root/'tps/win64',root/'tps/win64/python-3.8.3',root/'tps/win64/python-3.8.3/DLLs',root/'tps/mingw/6.2.0/win64.o/nt/bin',
             root/'tps/mingw/6.2.0/win64.o/nt/libexec/gcc/x86_64-w64-mingw32/6.2.0']
    dirs += [p for p in (root/'tps/win64').glob('jre*/bin/server')]
    dirs += [p for p in (root/'tps/win64').glob('jre*/bin')]
    env['PATH']=';'.join(str(p) for p in dirs)+';'+env['PATH']
    for key,value in dict(RDI_APPROOT=root,HDI_APPROOT=root,RDI_DATADIR=root/'data',
        RDI_BINDIR=root/'bin/unwrapped/win64.o',RDI_LIBDIR=root/'lib/win64.o',
        RDI_BINROOT=root/'bin',RDI_PLATFORM='win64',RDI_OPT_EXT='.o',
        RDI_INSTALLROOT=root.parents[1],RDI_INSTALLVERSION=root.name,XILINX_HLS=root,
        XILINX_VIVADO=root.parents[1]/'Vivado'/root.name,
        TCL_LIBRARY=root/'tps/tcl/tcl8.5',TK_LIBRARY=root/'tps/tcl/tk8.5').items():
        env[key]=value.as_posix() if isinstance(value,Path) else str(value)
    if root.parent.name!='Vivado':
        env['RDI_DATADIR']+=';'+(root.parents[1]/'Vivado'/root.name/'data').as_posix()
    env['RT_LIBPATH']=(root/'scripts/rt/data').as_posix()
    env['RT_TCL_PATH']=(root/'scripts/rt/base_tcl/tcl').as_posix()
    env['RDI_INSTALLVER']=root.name
    env['XILINX_VIVADO_HLS']=root.as_posix()
    jres=sorted((root/'tps/win64').glob('jre*'))
    if jres:
        env['RDI_JAVAROOT']=env['HDI_JAVAROOT']=env['JAVA_HOME']=jres[-1].as_posix()
        env['RDI_JAVACEFROOT']=(root/'tps/win64/java-cef-95.0.4638.69').as_posix()
        env['RDI_JAVAFXROOT']=(root/'tps/win64/javafx-sdk-17.0.1').as_posix()
    return env


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,default=Path('D:/vivado/Vitis_HLS/2023.1'))
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    command=[str(args.root/'bin/unwrapped/win64.o/vitis_hls.exe'),'-f',str(HERE/'hls/build_audio.tcl')]
    env=environment(args.root)
    env['GL_VISION_SOURCE']=HERE.as_posix();env['GL_VISION_OUTPUT']=args.output.resolve().as_posix()
    with (args.output/'hls-console.txt').open('w',encoding='utf-8') as log:
        result=subprocess.run(command,env=env,cwd=args.output,
            stdout=log,stderr=subprocess.STDOUT)
    text=(args.output/'hls-console.txt').read_text(encoding='utf-8',errors='replace')
    ip=args.output/'audio_hls/solution/impl/ip/component.xml'
    # HLS's generated pack.bat drops the required DLL/Tcl environment on this
    # Windows installation. Run the exact generated packaging Tcl directly.
    packaging=None
    script=ip.parent/'run_ippack.tcl'
    if not ip.exists() and script.exists() and 'Finished Command csynth_design' in text:
        vivado=args.root.parents[1]/'Vivado'/args.root.name
        with (args.output/'packaging-console.txt').open('w',encoding='utf-8') as log:
            packaging=subprocess.run([str(vivado/'bin/unwrapped/win64.o/vivado.exe'),'-mode','batch',
                '-nojournal','-source',script.resolve().as_posix()],cwd=ip.parent,
                env=environment(vivado),stdout=log,stderr=subprocess.STDOUT).returncode
    passed=ip.exists() and 'AUDIO_FFT_CSIM_PASS' in text and (result.returncode==0 or packaging==0)
    report=dict(passed=passed,exit_code=result.returncode,ip_generated=ip.exists(),
        source_sha256=hashlib.sha256((HERE/'hls/audio_fft.cpp').read_bytes()).hexdigest(),
        packaging_exit_code=packaging,twiddle_sha256=hashlib.sha256((HERE/'hls/audio_twiddle.h').read_bytes()).hexdigest(),scope='Audio FFT HLS C simulation, synthesis and IP export; no board deployment')
    (args.output/'result.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(text[-5000:]);print(json.dumps(report,indent=2))
    return int(not passed)


if __name__=='__main__':raise SystemExit(main())

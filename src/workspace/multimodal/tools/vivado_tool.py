"""Use installed native tools with explicit runtime paths on Windows."""
import argparse
import os
from pathlib import Path
import subprocess
import sys

def environment(root):
    root=Path(root).resolve(); env=dict(os.environ)
    env.update(XILINX_VIVADO=root.as_posix(),RDI_APPROOT=root.as_posix(),RDI_BINROOT=(root/'bin').as_posix(),
               RDI_DATADIR=(root/'data').as_posix(),RDI_LIBDIR=(root/'lib/win64.o').as_posix(),
               TCL_LIBRARY=(root/'tps/tcl/tcl8.5').as_posix(),RDI_BUILD='yes',HDI_APPROOT=root.as_posix(),RDI_PLATFORM='win64',RDI_OPT_EXT='.o')
    java=root/'tps/win64/jre17.0.3_7'
    env['RDI_JAVAROOT']=str(java);env['RDI_BASEROOT']=str(root.parent)
    env['RT_LIBPATH']=(root/'scripts/rt/data').as_posix()
    env['RT_TCL_PATH']=(root/'scripts/rt/base_tcl/tcl').as_posix()
    env['SYNTH_COMMON']=env['RT_LIBPATH']
    dirs=[root/'lib/win64.o',java/'bin/server',java/'bin',root/'tps/win64/python-3.8.3',root/'bin/unwrapped/win64.o',root/'bin',root/'tps/mingw/6.2.0/win64.o/nt/bin']
    env['PATH']=os.pathsep.join(str(x) for x in dirs)+os.pathsep+env.get('PATH','')
    return env

def main():
    p=argparse.ArgumentParser();p.add_argument('--root',default=os.environ.get('VIVADO_ROOT','D:/vivado/Vivado/2023.1'))
    p.add_argument('tool',choices=('vivado','xvlog','xelab','xsim'));p.add_argument('args',nargs=argparse.REMAINDER)
    a=p.parse_args();root=Path(a.root)
    exe=root/'bin/unwrapped/win64.o'/(a.tool+'.exe') if os.name=='nt' else root/'bin'/a.tool
    result=subprocess.run([str(exe)]+a.args,env=environment(root))
    return 1 if result.returncode else 0

if __name__=='__main__':sys.exit(main())

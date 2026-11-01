"""Host verification; no physical board or actuator commands are issued."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT=Path(__file__).resolve().parent


def main():
    report=ROOT/'report';report.mkdir(exist_ok=True)
    env=os.environ.copy();env['PYTHONUTF8']='1';env['PYTHONDONTWRITEBYTECODE']='1';env['GL_TEST_FATIGUE_MODEL']=str(ROOT/'brain_runtime/cyton_fatigue_overlap4.json')
    baseline=Path(env.get('GL_BASELINE_ROOT',str(ROOT.parent/'guardianloop_team_20261017_03')))
    if not baseline.exists():baseline=ROOT.parent
    env['GL_BASELINE_ROOT']=str(baseline)
    env['PYTHONPATH']=os.pathsep.join([str(ROOT/'brain_runtime'),str(ROOT/'runtime'),str(ROOT/'runtime/system_runtime'),str(baseline/'projects/codex_project'),str(baseline/'projects/codex_project/brain_eye_coexist/candidate/eye/src'),env.get('PYTHONPATH','')])
    compiler=shutil.which('gcc') or 'C:/mingw64/mingw64/bin/gcc.exe'
    env['PATH']=str(Path(compiler).parent)+os.pathsep+env['PATH']
    node=shutil.which('node') or 'E:/node/node.exe'
    commands=[('demo-python',[sys.executable,'-m','unittest','discover','-s','tests','-v']),
              ('eye-134',[sys.executable,'run_eye_regressions.py']),
              ('recording-core',[node,'--test','tests/test_demo_core.cjs']),
              ('original-phone',[node,'runtime/test_system_mobile.js']),
              ('brain-recovery',[sys.executable,'-m','unittest','test_primary_windows','test_primary_stream_recovery','-v']),
              ('fatigue-runtime',[sys.executable,'-c',"import types,sys,os,unittest;from pathlib import Path;m=types.ModuleType('audit_board_runtime');m.FATIGUE=Path(os.environ['GL_TEST_FATIGUE_MODEL']);sys.modules['audit_board_runtime']=m;import test_cyton_fatigue_runtime;unittest.main(module=test_cyton_fatigue_runtime,verbosity=2)"])]
    rows=[]
    for name,command in commands:
        result=subprocess.run(command,cwd=ROOT,env=env,text=True,encoding='utf-8',errors='replace',stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
        (report/(name+'.txt')).write_text(result.stdout,encoding='utf-8')
        rows.append(dict(name=name,exit_code=result.returncode));print(name,result.returncode,flush=True)
        if result.returncode:print(result.stdout)
    (report/'host-verification.json').write_text(json.dumps(rows,indent=2),encoding='utf-8')
    return int(any(r['exit_code'] for r in rows))


if __name__=='__main__':sys.exit(main())

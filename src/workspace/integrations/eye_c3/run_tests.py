"""Run new device tests and the unchanged archive regression suites on the host."""
import ast
import ctypes
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parent
BASELINE=Path(os.environ.get('GL_BASELINE_ROOT',str(ROOT.parent/'guardianloop_team_20261017_03')))
if not BASELINE.exists(): BASELINE=ROOT.parent
os.environ['GL_BASELINE_ROOT']=str(BASELINE)
os.environ['GL_TEST_EYE_ROOT']=str(BASELINE/'projects/codex_project/brain_eye_coexist/candidate/eye')
sys.path[:0]=[str(ROOT/'runtime'),str(ROOT/'runtime/system_runtime'),
              str(BASELINE/'projects/codex_project'),
              os.environ['GL_TEST_EYE_ROOT']+'/src',str(ROOT/'tests')]


def main():
    report=ROOT/'report';report.mkdir(exist_ok=True)
    compiler=shutil.which('gcc')
    if not compiler: raise RuntimeError('gcc is required for the host C reference check')
    host=report/('frame_fitter_host.dll' if os.name=='nt' else 'frame_fitter_host.so')
    subprocess.run([compiler,'-shared','-O2',str(ROOT/'runtime/frame_fitter.c'),'-o',str(host)],check=True)
    original=ctypes.CDLL
    def load(name,*args,**kwargs):
        return original(str(host) if Path(str(name)).name=='frame_fitter.so' else name,*args,**kwargs)
    suite=unittest.TestSuite()
    locations=[(ROOT/'tests','test_*.py'),
               (ROOT/'runtime/system_runtime/guardianloop_system','test_core.py'),
               (ROOT/'runtime/system_runtime/guardianloop_system','test_eye_entry.py'),
               (ROOT/'runtime/system_runtime/guardianloop_system','test_page_policy.py'),
               (ROOT/'runtime/system_runtime/guardianloop_system','test_live_inputs.py'),
               (ROOT/'runtime','test_system_hdmi.py'),
               (ROOT/'runtime','test_player_commands.py'),
               (ROOT/'runtime','test_playback_policy.py'),
               (BASELINE/'projects/codex_project/z15_hdmi_audio','test_page_audio.py')]
    for directory,pattern in locations:
        suite.addTests(unittest.TestLoader().discover(str(directory),pattern=pattern))
    stream=io.StringIO()
    with patch('ctypes.CDLL',side_effect=load):
        result=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
    (report/'tests.txt').write_text(stream.getvalue(),encoding='utf-8')
    sources=['media_player.py','system_hdmi.py','system_runtime/guardianloop_system/eye_devices.py',
             'system_runtime/guardianloop_system/device_link.py','system_runtime/guardianloop_system/c3_client.py']
    for source in sources:
        ast.parse((ROOT/'runtime'/source).read_text(encoding='utf-8'),feature_version=(3,8))
    summary=dict(tests=result.testsRun,failures=len(result.failures),errors=len(result.errors),
                 skipped=len(result.skipped),successful=result.wasSuccessful(),
                 python=sys.version.split()[0],syntax='Python 3.8 grammar',
                 native_fitter='host GCC build from unchanged C source; not ARM execution',
                 physical_devices_tested=False)
    (report/'tests.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    print(json.dumps(summary,indent=2))
    if not result.wasSuccessful():
        for _,detail in result.failures+result.errors: print(detail)
    return 0 if result.wasSuccessful() else 1


if __name__=='__main__':sys.exit(main())

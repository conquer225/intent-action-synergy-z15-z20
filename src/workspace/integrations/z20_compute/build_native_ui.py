"""Cross-build the integer-only glyph compositor for the actual ARMv7 board."""
import hashlib
import json
from pathlib import Path
import subprocess


def main():
    root=Path(__file__).resolve().parent
    base=json.loads((root/'build/navigator/camera-probe/compile.json').read_text())['command']
    output=root/'artifacts/headless/display/libz20_ui.so'
    command=base[:base.index('-static')]+['-O3','-shared','-fPIC','-fno-exceptions','-fno-rtti',
        str(root/'hardware/native/headless_ui.cpp'),'-o',str(output)]
    result=subprocess.run(command,capture_output=True,text=True)
    report=dict(command=command,exit_code=result.returncode,stdout=result.stdout,stderr=result.stderr)
    if result.returncode==0:report['sha256']=hashlib.sha256(output.read_bytes()).hexdigest()
    folder=root/'build/native-ui';folder.mkdir(exist_ok=True)
    (folder/'compile.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2));result.check_returncode()


if __name__=='__main__':main()

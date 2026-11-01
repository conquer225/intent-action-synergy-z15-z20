"""Build the board StereoBM adapter against the existing vendor OpenCV 3.4.3."""
import hashlib
import json
from pathlib import Path
import subprocess


def main():
    root=Path(__file__).resolve().parent
    base=json.loads((root/'build/native-person-dog/compile.json').read_text())['command']
    index=base.index(str(root/'hardware/native/person_dog_demo.cpp'))
    output=root/'artifacts/headless/display/libz20_stereo.so'
    command=base[:index]+[str(root/'hardware/native/stereo_board.cpp')]+base[index+1:]
    command[command.index('-o')+1]=str(output)
    result=subprocess.run(command,capture_output=True,text=True)
    report=dict(command=command,exit_code=result.returncode,stdout=result.stdout,stderr=result.stderr)
    if result.returncode==0:report['sha256']=hashlib.sha256(output.read_bytes()).hexdigest()
    folder=root/'build/native-stereo';folder.mkdir(exist_ok=True)
    (folder/'compile.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2));result.check_returncode()


if __name__=='__main__':main()

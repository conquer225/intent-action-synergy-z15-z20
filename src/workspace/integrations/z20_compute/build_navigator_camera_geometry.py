"""Build a read-back-checked SCCB crop command using the validated GPIO adapter."""
import hashlib
import json
from pathlib import Path
import subprocess

from z20_compute.navigator_camera_geometry import crop_plan


def main():
    root = Path(__file__).resolve().parent
    original = root/'build/navigator/camera-probe'
    output = root/'build/navigator/camera-geometry'
    output.mkdir(exist_ok=True)
    source = (original/'linux_gpio.cpp').read_text(encoding='utf-8')
    declaration = 'extern u8 sccb_read_reg16(u8,u16);'
    assert source.count(declaration)==1
    source = source.replace(declaration, declaration+'\nextern void sccb_write_reg16(u8,u16,u8);')
    plan = crop_plan()
    writes = '\n'.join('sccb_write_reg16(c,0x%04x,0x%02x);'%(a,v)
                       for a,v in plan['registers'])
    reads = '\n'.join('if(sccb_read_reg16(c,0x%04x)!=0x%02x)return 10;'%(a,v)
                      for a,v in plan['registers'])
    marker = ' for(int i=0;i<4;i++)close(fd[i]);return 0;'
    assert source.count(marker)==1
    crop = '''
 if(argc>2&&strcmp(argv[2],"crop")==0)for(unsigned c=0;c<2;c++){
 %s
 %s
 printf("CAM%%u_CROP=448,4,2176,1948 READBACK_OK\\n",c);fflush(stdout);
 }
'''%(writes,reads)
    source = source.replace(marker,crop+marker)
    path = output/'camera_geometry.cpp'
    path.write_text(source,encoding='utf-8')
    command = json.loads((original/'compile.json').read_text())['command']
    command = [str(path) if value==str(original/'linux_gpio.cpp') else value for value in command]
    target = output/'camera_geometry'
    command[command.index('-o')+1] = str(target)
    result = subprocess.run(command,capture_output=True,text=True)
    report = dict(command=command,exit_code=result.returncode,stdout=result.stdout,
                  stderr=result.stderr,plan=plan)
    if result.returncode==0:
        report['sha256']=hashlib.sha256(target.read_bytes()).hexdigest()
    (output/'compile.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2))
    result.check_returncode()


if __name__=='__main__':
    main()

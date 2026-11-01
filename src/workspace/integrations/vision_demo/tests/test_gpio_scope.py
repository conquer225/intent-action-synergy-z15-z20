import subprocess,tempfile,unittest
from pathlib import Path

class CameraGpioTests(unittest.TestCase):
    def test_sccb_initialization_preserves_linux_button_interrupts(self):
        root=Path(__file__).resolve().parents[1];source=root.parents[1]/'ps_eye_net'
        with tempfile.TemporaryDirectory() as d:
            exe=Path(d)/'gpio.exe'
            files=[root/'native/test_gpio_scope.c',source/'src/app/emio_sccb_cfg/emio_sccb_cfg.c']
            files += [source/'linux/driver'/n for n in ('xgpiops.c','xgpiops_g.c','xgpiops_sinit.c')]
            command=['C:/mingw64/mingw64/bin/gcc.exe','-std=c11','-Wall','-Wextra','-Werror',
                '-I'+str(source/'linux/include'),'-I'+str(source/'bsp/include'),'-I'+str(source/'src/app'),
                *map(str,files),'-o',str(exe)]
            r=subprocess.run(command,capture_output=True,text=True)
            self.assertEqual(r.returncode,0,r.stdout+r.stderr)
            r=subprocess.run([str(exe)],capture_output=True,text=True,timeout=10)
            self.assertEqual(r.returncode,0,r.stdout+r.stderr)
            self.assertIn('CAMERA_GPIO_COEXIST_PASS',r.stdout)

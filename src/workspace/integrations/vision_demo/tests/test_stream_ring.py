import subprocess,tempfile,unittest
from pathlib import Path
class AutonomousRingTests(unittest.TestCase):
    def test_dma_ring_restores_display_and_retains_memory_on_halt_failure(self):
        root=Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as d:
            exe=Path(d)/'ring.exe'
            r=subprocess.run(['C:/mingw64/mingw64/bin/gcc.exe','-std=c11','-Wall','-Wextra','-Werror',str(root/'native/test_stream_ring.c'),'-o',str(exe)],capture_output=True,text=True)
            self.assertEqual(r.returncode,0,r.stdout+r.stderr)
            r=subprocess.run([str(exe)],capture_output=True,text=True,timeout=10)
            self.assertEqual(r.returncode,0,r.stdout+r.stderr);self.assertIn('STREAM_RING_PASS',r.stdout)

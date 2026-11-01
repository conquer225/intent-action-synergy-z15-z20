import subprocess
import tempfile
import unittest
from pathlib import Path
from test_rtl import IVERILOG, VVP, ROOT


class VideoEpochTests(unittest.TestCase):
    def test_actual_stereo_geometry_handles_full_rows_bursts_and_ring_wrap(self):
        with tempfile.TemporaryDirectory() as directory:
            binary=Path(directory)/'geometry.vvp'
            p=subprocess.run([IVERILOG,'-g2012','-s','tb_video_geometry','-o',str(binary),
                str(ROOT/'hardware/rtl/z20_video_epoch.sv'),str(ROOT/'hardware/rtl/tb_video_geometry.sv')],
                capture_output=True,text=True)
            self.assertEqual(p.returncode,0,p.stdout+p.stderr)
            p=subprocess.run([VVP,str(binary)],capture_output=True,text=True,timeout=10)
            self.assertEqual(p.returncode,0,p.stdout+p.stderr)
            self.assertIn('PASS: four full stereo frames',p.stdout)

    def test_observer_mmio_is_readonly_and_holds_response_under_backpressure(self):
        with tempfile.TemporaryDirectory() as directory:
            binary = Path(directory)/'mmio.vvp'
            p = subprocess.run([IVERILOG, '-g2012', '-s', 'tb_video_observer', '-o', str(binary),
                    str(ROOT/'hardware/rtl/z20_video_epoch.sv'),
                    str(ROOT/'hardware/rtl/z20_video_observer.sv'),
                    str(ROOT/'hardware/rtl/tb_video_observer.sv')], capture_output=True, text=True)
            self.assertEqual(p.returncode, 0, p.stdout+p.stderr)
            p = subprocess.run([VVP, str(binary)], capture_output=True, text=True, timeout=10)
            self.assertEqual(p.returncode, 0, p.stdout+p.stderr)
            self.assertIn('PASS: observer MMIO', p.stdout)

    def test_passive_write_observer_fences_complete_frames_and_ring_wrap(self):
        self.assertTrue(IVERILOG and VVP, 'RTL simulator required')
        with tempfile.TemporaryDirectory() as directory:
            binary = Path(directory)/'observer.vvp'
            p = subprocess.run([IVERILOG, '-g2012', '-s', 'tb_video_epoch', '-o', str(binary),
                    str(ROOT/'hardware/rtl/z20_video_epoch.sv'),
                    str(ROOT/'hardware/rtl/tb_video_epoch.sv')], capture_output=True, text=True)
            self.assertEqual(p.returncode, 0, p.stdout+p.stderr)
            p = subprocess.run([VVP, str(binary)], capture_output=True, text=True, timeout=10)
            self.assertEqual(p.returncode, 0, p.stdout+p.stderr)
            self.assertIn('PASS: frame generation', p.stdout)


if __name__ == '__main__': unittest.main()

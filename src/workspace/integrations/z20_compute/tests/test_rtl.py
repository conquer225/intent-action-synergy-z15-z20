import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT/"build/tools/iverilog/mingw64/bin"
IVERILOG = shutil.which("iverilog") or (str(LOCAL/"iverilog.exe") if (LOCAL/"iverilog.exe").is_file() else None)
VVP = shutil.which("vvp") or (str(LOCAL/"vvp.exe") if (LOCAL/"vvp.exe").is_file() else None)


@unittest.skipUnless((IVERILOG and VVP) or shutil.which("vsim"), "RTL simulator unavailable")
class RtlTests(unittest.TestCase):
    def test_dac_clock_progress_and_midpoint_on_underrun(self):
        with tempfile.TemporaryDirectory() as directory:
            if not IVERILOG:
                tool = Path(shutil.which("vsim")).parent
                commands = [[str(tool/"vlib.exe"), "work"],
                            [str(tool/"vlog.exe"), "-sv", str(ROOT/"hardware/rtl/z20_dac_stream.sv"),
                             str(ROOT/"hardware/rtl/tb_dac.sv")],
                            [str(tool/"vsim.exe"), "-c", "work.tb_dac", "-do", "run -all; quit -f"]]
                for command in commands:
                    result = subprocess.run(command, cwd=directory, capture_output=True, text=True, timeout=30)
                    self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
                self.assertIn("PASS: DAC", result.stdout)
                self.assertNotIn("Fatal:", result.stdout)
                return
            binary = Path(directory)/"sim.vvp"
            compile_result = subprocess.run([IVERILOG, "-g2012", "-s", "tb_dac", "-o", str(binary),
                    str(ROOT/"hardware/rtl/z20_dac_stream.sv"), str(ROOT/"hardware/rtl/tb_dac.sv")],
                    capture_output=True, text=True, timeout=20)
            self.assertEqual(compile_result.returncode, 0, compile_result.stderr)
            result = subprocess.run([VVP, str(binary)], capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
            self.assertIn("PASS: DAC", result.stdout)


if __name__ == "__main__": unittest.main()

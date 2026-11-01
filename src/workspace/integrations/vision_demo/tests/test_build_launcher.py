"""The hardware launcher must use the prepared runtime and retain failure gates."""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import build_hardware


class HardwareLauncherTests(unittest.TestCase):
    def test_prepared_executable_and_environment_are_used_with_build_overrides(self):
        prepared = Path('private-runtime/vivado.exe')
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            with patch.object(build_hardware, 'prepare', return_value=(prepared, {'RDI_LIBDIR': 'private/lib', 'GL_VISION_SOURCE': 'stale'})), patch.object(build_hardware.subprocess, 'run', return_value=SimpleNamespace(returncode=0)) as process:
                build_hardware.run(Path('tool-root'), out/'build.tcl', out,
                                   {'RDI_LIBDIR': 'broken/lib', 'GL_VISION_SOURCE': 'actual-source'}, 'console')
            arguments, options = process.call_args
            self.assertEqual(arguments[0][0], str(prepared))
            self.assertEqual(options['env']['RDI_LIBDIR'], 'private/lib')
            self.assertEqual(options['env']['GL_VISION_SOURCE'], 'actual-source')

    def test_access_violation_remains_a_build_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            with patch.object(build_hardware, 'prepare', return_value=(Path('vivado.exe'), {})), patch.object(build_hardware.subprocess, 'run', return_value=SimpleNamespace(returncode=0xC0000005)):
                with self.assertRaisesRegex(RuntimeError, 'console failed'):
                    build_hardware.run(Path('tool-root'), out/'build.tcl', out, {}, 'console')

"""Check the actual Windows helper layout without running or programming a board."""
import hashlib,os,unittest
from pathlib import Path


class VivadoEnvironmentTests(unittest.TestCase):
    @unittest.skipUnless(os.name=='nt' and Path('D:/vivado/Vivado/2023.1').is_dir(),'local Windows Vivado unavailable')
    def test_scanner_derived_from_library_root_has_its_runtime_dependencies(self):
        from tool_environment import prepare
        root=Path('D:/vivado/Vivado/2023.1')
        executable,environment=prepare(root)
        library=Path(environment['RDI_LIBDIR'])
        scanner=library.parent.parent/'bin/unwrapped/win64.o/srcscanner.exe'
        self.assertTrue(scanner.is_file())
        self.assertTrue((scanner.parent/'librdi_common.dll').is_file(),'derived scanner still lacks its DLLs')
        self.assertEqual(hashlib.sha256(scanner.read_bytes()).digest(),hashlib.sha256((root/'bin/unwrapped/win64.o/srcscanner.exe').read_bytes()).digest())
        self.assertEqual(environment['RDI_APPROOT'],root.as_posix())
        self.assertTrue(executable.is_file())

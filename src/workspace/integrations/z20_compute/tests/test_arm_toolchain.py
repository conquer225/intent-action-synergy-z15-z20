import os
import hashlib
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest

from tool_environment import prepare_arm_compiler


class ARMToolchainTests(unittest.TestCase):
    @unittest.skipUnless(os.name == 'nt' and Path('D:/vivado/Vitis/2023.1').is_dir(),
                         'installed Windows ARM toolchain required')
    def test_baremetal_compiler_produces_arm_object_without_installation_changes(self):
        root = Path('D:/vivado/Vitis/2023.1')
        original = root/'gnu/aarch32/nt/gcc-arm-none-eabi/bin/arm-none-eabi-gcc.exe'
        original_hash = hashlib.sha256(original.read_bytes()).hexdigest()
        compiler, environment = prepare_arm_compiler(root)
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)/'probe.c'
            output = Path(directory)/'probe.o'
            source.write_text('#include <stdint.h>\nuint32_t add(uint32_t x) { return x+7; }\n')
            result = subprocess.run([str(compiler), '-mcpu=cortex-a9', '-mfloat-abi=hard',
                '-mfpu=vfpv3', '--sysroot='+str(root/'gnu/aarch32/nt/gcc-arm-none-eabi/aarch32-xilinx-eabi'),
                '-c', str(source), '-o', str(output)], env=environment,
                capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
            data = output.read_bytes()
            self.assertEqual(data[:6], b'\x7fELF\x01\x01')
            self.assertEqual(struct.unpack_from('<H', data, 18)[0], 40)
            self.assertNotEqual(compiler.parent, root/'gnu/aarch32/nt/gcc-arm-none-eabi/bin')
            self.assertEqual(hashlib.sha256(original.read_bytes()).hexdigest(), original_hash)


if __name__ == '__main__': unittest.main()

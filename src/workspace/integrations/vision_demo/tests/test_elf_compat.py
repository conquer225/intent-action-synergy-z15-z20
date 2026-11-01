import unittest
from elf_compat import validate_arm_runtime

def arm_elf(version):
 data=bytearray(52);data[:6]=b'\x7fELF\x01\x01';data[18:20]=(40).to_bytes(2,'little')
 return bytes(data)+b'\0GLIBC_'+version.encode()+b'\0'

class ElfCompatibilityTests(unittest.TestCase):
 def test_board_231_rejects_newer_startup_and_accepts_older_runtime(self):
  with self.assertRaisesRegex(ValueError,'2.34'):validate_arm_runtime(arm_elf('2.34'),(2,31))
  self.assertEqual(validate_arm_runtime(arm_elf('2.17'),(2,31)),[(2,17)])
  with self.assertRaisesRegex(ValueError,'ARM'):validate_arm_runtime(b'not executable',(2,31))

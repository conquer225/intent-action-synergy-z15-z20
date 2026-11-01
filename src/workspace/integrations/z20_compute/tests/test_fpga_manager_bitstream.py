import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from z20_compute.bitstream import to_fpga_manager_bytes


class FpgaManagerBitstreamTests(unittest.TestCase):
    def test_swaps_each_32_bit_word_and_sync_word(self):
        raw = bytes.fromhex("000000bb 11220044 aa995566 20000000")
        self.assertEqual(
            to_fpga_manager_bytes(raw),
            bytes.fromhex("bb000000 44002211 665599aa 00000020"),
        )

    def test_rejects_unaligned_or_missing_sync(self):
        with self.assertRaises(ValueError):
            to_fpga_manager_bytes(b"abc")
        with self.assertRaises(ValueError):
            to_fpga_manager_bytes(bytes.fromhex("000000bb 11220044"))


if __name__ == "__main__":
    unittest.main()

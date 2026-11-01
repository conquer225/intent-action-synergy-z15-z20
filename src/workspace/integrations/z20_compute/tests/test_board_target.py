import struct
import unittest

from z20_compute.board_target import validate_bit_target


def bit_image(part):
    # Xilinx .bit header: magic, tagged strings, then big-endian payload size.
    data = b'\x00\x09' + b'\x0f\xf0' * 4 + b'\x00' + b'\x00\x01'
    for tag, value in ((b'a', b'test\0'), (b'b', part.encode()+b'\0'),
                       (b'c', b'2026/10/23\0'), (b'd', b'23:20:00\0')):
        data += tag + struct.pack('>H', len(value)) + value
    return data + b'e' + struct.pack('>I', 4) + b'\xaa\x99\x55\x66'


class BoardTargetTests(unittest.TestCase):
    def test_navigator_rejects_new_z20_package_before_programming(self):
        with self.assertRaisesRegex(ValueError, 'clg400'):
            validate_bit_target('Alientek Navigator Zynq Development Board',
                                0x23727093, bit_image('7z020clg484'))

    def test_matching_package_and_silicon_are_accepted_with_payload_location(self):
        image = bit_image('7z020clg400')
        result = validate_bit_target('Alientek Navigator Zynq Development Board',
                                     0x23727093, image)
        self.assertEqual(result['target'], 'navigator-7020-clg400')
        self.assertEqual(image[result['payload_offset']:], b'\xaa\x99\x55\x66')

    def test_unknown_carrier_wrong_silicon_and_truncated_payload_are_rejected(self):
        image = bit_image('7z020clg400')
        for model, chip, data in [('generic Zynq', 0x23727093, image),
                                  ('Navigator', 0x23722093, image),
                                  ('Navigator', 0x23727093, image[:-1])]:
            with self.subTest(model=model, chip=chip, size=len(data)):
                with self.assertRaises(ValueError):
                    validate_bit_target(model, chip, data)


if __name__ == '__main__':
    unittest.main()

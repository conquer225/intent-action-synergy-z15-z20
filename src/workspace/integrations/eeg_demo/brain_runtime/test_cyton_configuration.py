"""Fixed-eight command handshake and reboot detection; no real hardware."""
import os
import socket
import threading
import time
import unittest
from unittest.mock import patch

if os.name == 'posix':
    import cyton_guardianloop as live


@unittest.skipUnless(os.name == 'posix', 'Acquisition uses Linux serial APIs')
class ConfigurationTests(unittest.TestCase):
    def test_version_and_eight_matching_channel_acknowledgements(self):
        commands = []
        replies = [b'v3.1.1'] + [f'Success: Channel set for {n}'.encode() for n in range(1, 9)]
        def exchange(fd, command):
            commands.append(command)
            return replies.pop(0)
        with patch.object(live, 'command_response', side_effect=exchange), \
                patch.object(live, 'write_command') as write, patch.object(live.time, 'sleep'):
            result = live.configure_eeg_channels(17)
        self.assertEqual(commands, [b'V']+[f'x{n}060110X'.encode() for n in range(1, 9)])
        write.assert_called_once_with(17, b'c')
        self.assertEqual(result, dict(firmware='v3.1.1', acknowledged_channels=list(range(1,9))))
        self.assertFalse(replies)

    def test_bad_ack_never_continues_to_later_channels(self):
        with patch.object(live, 'command_response', side_effect=[b'v3.1.1', b'Failure: too few chars']) as response, \
                patch.object(live, 'write_command'), patch.object(live.time, 'sleep'):
            with self.assertRaisesRegex(ValueError, 'channel 1'):
                live.configure_eeg_channels(17)
        self.assertEqual(response.call_count, 2)

    def test_offline_device_gets_no_multibyte_settings(self):
        with patch.object(live, 'command_response', side_effect=TimeoutError('offline')), \
                patch.object(live, 'write_command') as write:
            with self.assertRaises(TimeoutError):
                live.configure_eeg_channels(17)
        write.assert_not_called()

    def test_ack_for_another_channel_is_not_success(self):
        with patch.object(live, 'command_response', side_effect=[b'v3.1.1', b'Success: Channel set for 8']), \
                patch.object(live, 'write_command'), patch.object(live.time, 'sleep'):
            with self.assertRaisesRegex(ValueError, 'channel 1'):
                live.configure_eeg_channels(17)

    def test_unknown_firmware_gets_no_channel_settings(self):
        with patch.object(live, 'command_response', return_value=b'Failure: Device down'), \
                patch.object(live, 'write_command') as write:
            with self.assertRaisesRegex(ValueError, 'firmware'):
                live.configure_eeg_channels(17)
        write.assert_not_called()

    def test_partial_command_write_is_an_error(self):
        with patch.object(live.os, 'write', return_value=2), patch.object(live.termios, 'tcdrain') as drain:
            with self.assertRaisesRegex(OSError, 'Incomplete'):
                live.write_command(17, b'x1060110X')
        drain.assert_not_called()

    def test_fragmented_response_stops_at_eot(self):
        peer, client = socket.socketpair()
        def reply():
            self.assertEqual(peer.recv(32), b'V')
            for part in (b'v3.', b'1.1$', b'$$'):
                peer.sendall(part); time.sleep(.01)
        worker = threading.Thread(target=reply)
        worker.start()
        try:
            with patch.object(live.termios, 'tcflush'), patch.object(live.termios, 'tcdrain'):
                self.assertEqual(live.command_response(client.fileno(), b'V', timeout=.5), b'v3.1.1')
        finally:
            worker.join(timeout=1); peer.close(); client.close()

    def test_response_timeout_is_bounded(self):
        peer, client = socket.socketpair()
        try:
            began = time.monotonic()
            with patch.object(live.termios, 'tcflush'), patch.object(live.termios, 'tcdrain'):
                with self.assertRaises(TimeoutError):
                    live.command_response(client.fileno(), b'V', timeout=.05)
            self.assertLess(time.monotonic()-began, .3)
        finally:
            peer.close(); client.close()


@unittest.skipUnless(os.name == 'posix', 'Reader uses Linux fork')
class BootReaderTests(unittest.TestCase):
    def test_complete_boot_banner_requires_reconfiguration(self):
        r, w = os.pipe()
        os.write(w, b'OpenBCI V3 8-16 channel\r\nADS1299 Device ID: 0x3E\r\nFirmware: v3.1.1\r\n$$$')
        reader = live.packets(r, .5)
        try:
            with self.assertRaises(live.CytonReaderError) as caught:
                next(reader)
            self.assertEqual(caught.exception.report['kind'], 'device_restarted')
        finally:
            reader.close(); os.close(r); os.close(w)

    def test_fragmented_boot_trailer_is_detected_without_another_packet(self):
        r, w = os.pipe()
        def chunks():
            os.write(w, b'OpenBCI V3 8-16 channel\r\nADS1299 Device ID: 0x3E\r\n')
            time.sleep(.08); os.write(w, b'$$$')
        writer = threading.Thread(target=chunks); writer.start()
        reader = live.packets(r, 1)
        try:
            with self.assertRaises(live.CytonReaderError) as caught:
                next(reader)
            self.assertEqual(caught.exception.report['kind'], 'device_restarted')
        finally:
            reader.close(); writer.join(timeout=1); os.close(r); os.close(w)

    def test_banner_bytes_inside_valid_eeg_do_not_trigger_reconfiguration(self):
        r, w = os.pipe()
        first = b'\xa0\x00'+b'OpenBCI V3 ADS1299 Device ID:' + b'\0\0' + b'\xc0'
        first = first[:32]+b'\xc0'
        second = b'\xa0\x01$$$'+bytes(27)+b'\xc0'
        self.assertEqual(len(first), 33); self.assertEqual(len(second), 33)
        os.write(w, first+second)
        reader = live.packets(r, 1)
        try:
            self.assertEqual(next(reader)[0], first)
            self.assertEqual(next(reader)[0], second)
        finally:
            reader.close(); os.close(r); os.close(w)


if __name__ == '__main__':
    unittest.main()

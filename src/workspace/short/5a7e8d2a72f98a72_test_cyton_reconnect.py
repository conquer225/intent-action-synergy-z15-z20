"""Reconnect state/ownership checks using generated packets, never live USB."""
import contextlib
import io
import os
import unittest
from unittest.mock import Mock, patch

if os.name == 'posix':
    import cyton_guardianloop as live


def frame(sequence, zero_channels=()):
    values=[0 if i+1 in zero_channels else 1000+i for i in range(8)]
    return bytes((0xa0,sequence%256))+b''.join(v.to_bytes(3,'big') for v in values)+bytes(6)+b'\xc0'


@unittest.skipUnless(os.name == 'posix','Acquisition uses Linux descriptors')
class ReconnectTests(unittest.TestCase):
    def setUp(self):
        self.clock=100.;self.active=False;self.events=[];self.opened=0
        self.stack=contextlib.ExitStack();self.addCleanup(self.stack.close)
        self.stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
        self.stack.enter_context(patch.object(live.time,'sleep'))
        self.stack.enter_context(patch.object(live.time,'monotonic',side_effect=lambda:self.clock))
        self.stack.enter_context(patch.object(live.termios,'tcflush'))
        self.config=self.stack.enter_context(patch.object(live,'configure_eeg_channels',side_effect=self.configure))
        self.write=self.stack.enter_context(patch.object(live,'write_command'))
        self.idle=Mock();self.started=Mock();self.reset=Mock()

    def configure(self,fd):
        self.assertFalse(self.active,'Configuration raced the old serial reader')
        self.events.append('configure')

    def reader(self,scenario):
        def packets(*args,**kwargs):
            self.opened+=1;self.active=True;self.events.append('reader_open')
            try:yield from scenario(self.opened,kwargs['on_idle'])
            finally:self.active=False;self.events.append('reader_closed')
        self.stack.enter_context(patch.object(live,'packets',side_effect=packets))

    def run_stream(self,wait=True):
        return list(live.configured_packets(17,5,on_idle=self.idle,on_configured=self.started,
                    on_reconfigure=self.reset,wait_for_data=wait))

    def test_silent_restart_closes_reader_and_reinitializes_without_a_boot_banner(self):
        def scenario(at,idle):
            yield frame(0),0,self.clock
            if at==1:self.clock+=5.1;idle(self.clock)
        self.reader(scenario);rows=self.run_stream()
        self.assertEqual(len(rows),2);self.assertEqual(self.config.call_count,2)
        self.assertEqual(self.events,['configure','reader_open','reader_closed','configure','reader_open','reader_closed'])
        self.reset.assert_called_once_with('CYTON_NO_PACKETS_RECONNECT')

    def test_short_silence_does_not_rewrite_configuration(self):
        def scenario(at,idle):
            yield frame(0),0,self.clock
            self.clock+=.7;idle(self.clock)
            yield frame(1),0,self.clock
        self.reader(scenario);self.assertEqual(len(self.run_stream()),2)
        self.config.assert_called_once();self.reset.assert_not_called()

    def test_device_restart_reconfigures_but_usb_io_error_is_not_swallowed(self):
        def scenario(at,idle):
            if at==1:raise live.CytonReaderError({'kind':'device_restarted'})
            yield frame(0),0,self.clock
        self.reader(scenario);self.assertEqual(len(self.run_stream()),1)
        self.reset.assert_called_once_with('CYTON_DEVICE_RESTARTED')
        self.assertEqual(self.config.call_count,2)

    def test_usb_io_error_leaves_service_recovery_in_charge(self):
        def scenario(at,idle):
            raise live.CytonReaderError({'kind':'serial_io_error','errno':5})
            yield
        self.reader(scenario)
        with self.assertRaises(live.CytonReaderError):self.run_stream()
        self.config.assert_called_once();self.assertFalse(self.active)

    def test_offline_configuration_waits_without_starting_a_reader_or_stream(self):
        self.config.side_effect=[TimeoutError('offline'),TimeoutError('offline'),None]
        self.reader(lambda at,idle:iter([(frame(0),0,self.clock)]))
        self.assertEqual(len(self.run_stream()),1)
        self.assertEqual(self.opened,1);self.assertEqual(self.config.call_count,3)
        self.assertEqual([c.args[1] for c in self.write.call_args_list],[b's',b's',b's',b'b'])

    def test_unconfirmed_channel_does_not_start_until_all_settings_succeed(self):
        self.config.side_effect=[live.CytonConfigurationError('channel 3'),None]
        self.reader(lambda at,idle:iter([(frame(0),0,self.clock)]))
        self.assertEqual(len(self.run_stream()),1);self.assertEqual(self.opened,1)
        self.assertEqual(self.started.call_count,1)

    def test_partial_zero_channels_get_one_retry_not_an_endless_reset_loop(self):
        self.reader(lambda at,idle:((frame(n,(1,3,4,6,7)),0,self.clock) for n in range(300)))
        rows=self.run_stream()
        self.assertEqual(len(rows),550);self.assertEqual(self.config.call_count,2)
        self.reset.assert_called_once_with('CYTON_MULTIPLE_ZERO_CHANNELS')

    def test_a_single_zero_or_constant_nonzero_electrode_does_not_reset_all_channels(self):
        self.reader(lambda at,idle:((frame(n,(4,)),0,self.clock) for n in range(300)))
        self.assertEqual(len(self.run_stream()),300)
        self.config.assert_called_once();self.reset.assert_not_called()

    def test_parser_faults_are_not_used_as_clean_channel_verification(self):
        self.reader(lambda at,idle:((frame(n,(1,3,4,6,7)),1,self.clock) for n in range(300)))
        self.assertEqual(len(self.run_stream()),300);self.config.assert_called_once()
        self.reset.assert_not_called()

    def test_finite_diagnostic_does_not_turn_into_an_automatic_retry(self):
        self.config.side_effect=TimeoutError('offline')
        with self.assertRaises(TimeoutError):self.run_stream(wait=False)
        self.config.assert_called_once();self.started.assert_not_called()


if __name__=='__main__':unittest.main()

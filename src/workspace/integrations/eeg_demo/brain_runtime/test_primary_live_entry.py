"""The production async path is opt-in and restricted to the fixed ARM contract."""
import os
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

import guardianloop_acquisition as entry
if os.name=='posix':
    import cyton_guardianloop as live


class LiveEntryTests(unittest.TestCase):
    def test_service_default_and_async_opt_in(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            for mode, expected in (('sync',False),('async',True)):
                with patch.dict(os.environ, {'GL_PRIMARY_EXECUTION':mode}, clear=True):
                    args=entry.acquisition_args(['--windows','0'],root,root/'absent')
                self.assertEqual('--live-primary-worker' in args,expected)
                self.assertIn('--wait-for-data',args)
            with patch.dict(os.environ, {'GL_PRIMARY_EXECUTION':'typo'}, clear=True):
                with self.assertRaises(ValueError):entry.acquisition_args([],root,root/'absent')

    def test_cli_cannot_select_a_replay_or_override_service_policy(self):
        for args in (['--live-primary-worker'],['--isolated-primary-worker'],
                     ['--isolated-reader-batch'],['--isolated-primary-checkpoint']):
            with self.assertRaises(ValueError):entry.acquisition_args(args,Path('/unused'))

    def contract(self):
        root=Path('/home/xilinx/jupyter_notebooks/guardianloop_pynq')
        return SimpleNamespace(port='/dev/serial/by-id/usb-FTDI_FT231X_USB_UART_D309LDXY-if00-port0',
            filter_backend='arm',wait_for_data=True,windows=0,esp32_url='',
            microvolts_per_count=live.DEFAULT_UV_PER_COUNT,
            status_file='/run/guardianloop/status.json',telemetry_file='/run/guardianloop/telemetry.json',
            fatigue_model=str(root/'cyton_fatigue_overlap4.json'),
            covariance_model=str(root/'gameemo_covariance_svm.npz'),
            isolated_primary_worker=False,isolated_reader_batch=False,isolated_primary_checkpoint=False)

    @unittest.skipUnless(os.name=='posix','The acquisition contract requires Linux')
    def test_contract_rejects_foreign_input_model_scale_and_output(self):
        live.validate_live_primary(self.contract(),live.DEFAULT_CHANNEL_MAP)
        changes={'port':'/dev/null','filter_backend':'pl','wait_for_data':False,'windows':1,
            'esp32_url':'http://controller','microvolts_per_count':1.0,'status_file':'/tmp/status',
            'telemetry_file':'/tmp/telemetry','fatigue_model':'/tmp/model',
            'covariance_model':'/tmp/model','isolated_primary_worker':True,
            'isolated_reader_batch':True,'isolated_primary_checkpoint':True}
        for key,value in changes.items():
            args=self.contract();setattr(args,key,value)
            with self.subTest(key=key),self.assertRaises(ValueError):
                live.validate_live_primary(args,live.DEFAULT_CHANNEL_MAP)
        with self.assertRaises(ValueError):live.validate_live_primary(self.contract(),{'C3':0})


if __name__=='__main__':unittest.main()

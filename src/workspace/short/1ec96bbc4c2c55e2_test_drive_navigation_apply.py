import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import drive_navigation_apply as apply


class TransientWebRecoveryTests(unittest.TestCase):
    def test_missing_transient_server_is_recreated_without_expiry(self):
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory)
            (base/'state.json').write_text(json.dumps({'user_controlled':True}))
            with patch.object(apply,'BASE',base), patch.object(apply,'control',return_value='not-found') as control, \
                    patch.object(apply.subprocess,'run') as run:
                apply.start_server()
            control.assert_called_once_with('show',apply.SERVER,'-p','LoadState','--value')
            args=run.call_args.args[0]
            self.assertEqual(args[0],'systemd-run')
            self.assertIn(str(base/'media_server.py'),args)
            self.assertIn(str(base/'access.key'),args)
            self.assertFalse(any('RuntimeMaxSec' in arg for arg in args))

    def test_loaded_server_uses_existing_unit(self):
        with patch.object(apply,'control',side_effect=['loaded','']) as control, \
                patch.object(apply.subprocess,'run') as run:
            apply.start_server()
        self.assertEqual(control.call_args.args,('start',apply.SERVER))
        run.assert_not_called()

    def test_stopping_missing_server_does_not_abort_rollback(self):
        with patch.object(apply,'control',return_value='not-found') as control:
            apply.stop_server()
        control.assert_called_once_with('show',apply.SERVER,'-p','LoadState','--value')


if __name__=='__main__':
    unittest.main()

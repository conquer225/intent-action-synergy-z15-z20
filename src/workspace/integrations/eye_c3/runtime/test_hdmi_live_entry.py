import hashlib
from pathlib import Path
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from hdmi_live_entry import MODULES, load_modules
import hdmi_live_entry as entry


class ModuleTests(unittest.TestCase):
    def setUp(self):
        self.saved = {name: sys.modules.get(name) for name in MODULES}
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        sources = {'ssvep_free': 'value = 23\n',
                   'ssvep_hdmi': 'from ssvep_free import value\n',
                   'ssvep_cue_runtime': 'from ssvep_hdmi import value\n'}
        self.hashes = {}
        for name, source in sources.items():
            raw = source.encode()
            (self.root / (name + '.py')).write_bytes(raw)
            self.hashes[name] = hashlib.sha256(raw).hexdigest()

    def tearDown(self):
        for name, module in self.saved.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module
        self.directory.cleanup()

    def test_exact_dependencies_are_loaded_in_order(self):
        self.assertEqual(load_modules(self.root, self.hashes).value, 23)

    def test_all_hashes_checked_before_any_module_replacement(self):
        self.hashes['ssvep_cue_runtime'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'Candidate module changed'):
            load_modules(self.root, self.hashes)
        self.assertIs(sys.modules.get('ssvep_free'), self.saved['ssvep_free'])

    def test_extra_module_is_not_allowed(self):
        self.hashes['cyton_guardianloop'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'three audited'):
            load_modules(self.root, self.hashes)


class ProducerScheduleTests(unittest.TestCase):
    def test_original_worker_receives_original_arguments_after_schedule(self):
        events=[]
        cue=SimpleNamespace(SSVEPCueRuntime=object())
        worker=SimpleNamespace(_worker=lambda *args:events.append(('worker',args)))
        with patch.object(entry,'prepare',return_value=({},cue)), \
                patch.dict(entry.os.environ,GL_HDMI_LIVE_STATE='/verified/state.json'), \
                patch.object(entry.os,'PRIO_PROCESS',0,create=True), \
                patch.object(entry.os,'sched_setaffinity',create=True,
                             side_effect=lambda *a:events.append(('affinity',a))), \
                patch.object(entry.os,'setpriority',create=True,
                             side_effect=lambda *a:events.append(('priority',a))), \
                patch.dict(sys.modules,ssvep_acquisition=worker):
            entry.acquisition_worker('connection','queue','weights')
        self.assertEqual(events,[('affinity',(0,{0})),('priority',(0,0,-5)),
                                 ('worker',('connection','queue','weights'))])
        self.assertIs(worker.SSVEPCueRuntime,cue.SSVEPCueRuntime)

    def test_schedule_failure_does_not_start_unverified_worker(self):
        worker=SimpleNamespace(_worker=Mock())
        with patch.object(entry,'prepare',return_value=({},SimpleNamespace(SSVEPCueRuntime=object()))), \
                patch.dict(entry.os.environ,GL_HDMI_LIVE_STATE='/verified/state.json'), \
                patch.object(entry.os,'sched_setaffinity',create=True,
                             side_effect=PermissionError('schedule denied')), \
                patch.dict(sys.modules,ssvep_acquisition=worker):
            with self.assertRaisesRegex(PermissionError,'schedule denied'):
                entry.acquisition_worker('unchanged')
        worker._worker.assert_not_called()


if __name__ == '__main__':
    unittest.main()

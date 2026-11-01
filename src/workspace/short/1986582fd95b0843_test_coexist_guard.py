import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import coexist_guard as guard


class AdmissionTests(unittest.TestCase):
    def setUp(self):
        self.startup = {
            'state': 'ready', 'boot_id': 'boot', 'pl': {'used_by_current_cap': False},
            'tasks': {name: {'backend': 'arm'} for name in (
                'filter_quality', 'emotion', 'fatigue', 'seed_candidate', 'ssvep_candidate', 'mi_virtual')}}
        self.startup['tasks']['filter_quality']['channels'] = list(guard.CHANNELS)
        self.startup['tasks']['mi_virtual']['physical_control'] = False
        self.process = {'state': 'active', 'pid': 40,
                        'argv': ['python3', str(guard.BRAIN_ROOT / 'guardianloop_acquisition.py')],
                        'environment': {}}

    def check(self, modules=(), keeper=False):
        guard.check_arm_contract(self.startup, self.process, 'boot', modules, keeper)

    def test_current_fixed_cap_arm_is_admitted_without_mutation(self):
        before = copy.deepcopy((self.startup, self.process))
        self.check()
        self.assertEqual(before, (self.startup, self.process))

    def test_each_pl_backend_is_rejected(self):
        for task in self.startup['tasks']:
            with self.subTest(task=task):
                self.startup['tasks'][task]['backend'] = 'pl'
                with self.assertRaises(RuntimeError):self.check()
                self.startup['tasks'][task]['backend'] = 'arm'

    def test_kernel_dma_owner_or_keeper_is_rejected(self):
        for modules, keeper in ((['gldma_owner'], False), ([], True)):
            with self.assertRaises(RuntimeError):self.check(modules, keeper)

    def test_stale_boot_unready_selftest_or_pl_dependency_is_rejected(self):
        for name, value in (('boot_id', 'old'), ('state', 'checking'), ('pl', {})):
            original = self.startup[name]
            self.startup[name] = value
            with self.assertRaises(RuntimeError):self.check()
            self.startup[name] = original

    def test_bad_cap_model_override_and_missing_task_are_rejected(self):
        for key, value in (('GL_CHANNEL_MAP', 'F3,F4,C3,C4,O1,O2,T7,T8'),
                           ('GL_COVARIANCE_MODEL', '/tmp/other.npz')):
            self.process['environment'] = {key: value}
            with self.assertRaises(RuntimeError):self.check()
        self.process['environment'] = {}
        del self.startup['tasks']['fatigue']
        with self.assertRaises(RuntimeError):self.check()

    def test_pl_filter_and_channel_override_are_rejected(self):
        base = self.process['argv'][:]
        for arguments in (['--filter-backend', 'pl'], ['--filter-backend=pl'], ['--channel-map', ','.join(guard.CHANNELS)]):
            self.process['argv'] = base + arguments
            with self.assertRaises(RuntimeError):self.check()

    def test_inactive_service_unknown_entry_and_physical_control_rejected(self):
        self.process['state'] = 'inactive'
        with self.assertRaises(RuntimeError):self.check()
        self.process['state'] = 'active'
        self.process['argv'] = ['python3', 'cyton_guardianloop.py']
        with self.assertRaises(RuntimeError):self.check()
        self.process['argv'] = [str(guard.BRAIN_ROOT / 'guardianloop_acquisition.py')]
        self.startup['tasks']['mi_virtual']['physical_control'] = True
        with self.assertRaises(RuntimeError):self.check()

    def test_release_edits_are_not_silently_accepted(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'a.py').write_text('original')
            manifest = root / 'release_manifest.json'
            manifest.write_text(json.dumps({'channels': list(guard.CHANNELS),
                                            'files': {'a.py': guard.file_sha(root / 'a.py')}}))
            with patch.object(guard, 'EXPECTED_MANIFEST', guard.file_sha(manifest)):
                guard.verify_release(root)
                (root / 'a.py').write_text('changed')
                with self.assertRaises(RuntimeError):guard.verify_release(root)
            with self.assertRaises(RuntimeError):guard.verify_release(root)

    def test_display_wait_does_not_relax_hardware_or_boot_contract(self):
        self.process={'state':'inactive','pid':0}
        self.assertFalse(guard.check_arm_contract(self.startup,self.process,'boot',(),False,
                                                 require_acquisition=False))
        with self.assertRaises(RuntimeError):self.check()
        for modules,keeper in ((('gldma_owner',),False),((),True)):
            with self.assertRaises(RuntimeError):
                guard.check_arm_contract(self.startup,self.process,'boot',modules,keeper,False)
        self.startup['tasks']['emotion']['backend']='pl'
        with self.assertRaises(RuntimeError):
            guard.check_arm_contract(self.startup,self.process,'boot',(),False,False)


class RestartTests(unittest.TestCase):
    setUp = AdmissionTests.setUp

    def runtime(self,allow=True):
        instance=guard.CoexistGuard.__new__(guard.CoexistGuard)
        instance.shared=False;instance.boot='boot';instance.process=copy.deepcopy(self.process)
        instance.allow_acquisition_restart=allow
        self.startup['release_id']='audited'
        return instance

    def observe(self,instance,process,require=False):
        with patch.object(guard,'process_contract',return_value=process), \
                patch.object(Path,'read_text',side_effect=lambda *a,**k:json.dumps(self.startup) if a[0]==guard.STARTUP else '',autospec=True), \
                patch.object(Path,'exists',return_value=False):
            return instance.check_runtime(require_acquisition=require)

    def test_initial_admission_still_requires_running_acquisition(self):
        with self.assertRaises(RuntimeError):
            self.observe(self.runtime(),{'state':'inactive','pid':0},require=True)

    def test_opt_in_pause_revokes_identity_then_revalidates_restart(self):
        instance=self.runtime()
        self.assertFalse(self.observe(instance,{'state':'deactivating','pid':40}))
        self.assertIsNone(instance.acquisition_identity)
        self.assertFalse(self.observe(instance,{'state':'inactive','pid':0}))
        resumed=dict(self.process,pid=41,start_ticks=123)
        with patch.object(guard,'verify_release',return_value={'release_id':'audited'}) as verify:
            self.assertTrue(self.observe(instance,resumed));verify.assert_called_once_with(guard.BRAIN_ROOT)
        self.assertEqual(instance.acquisition_identity,(41,123))

    def test_legacy_eye_session_does_not_accept_pid_change(self):
        with self.assertRaises(RuntimeError):
            self.observe(self.runtime(allow=False),dict(self.process,pid=41))

    def test_restart_rejects_unverified_release_and_configuration(self):
        instance=self.runtime()
        resumed=dict(self.process,pid=41)
        with patch.object(guard,'verify_release',side_effect=RuntimeError('changed files')):
            with self.assertRaisesRegex(RuntimeError,'changed files'):self.observe(instance,resumed)
        bad=dict(resumed,argv=['python3','other.py'])
        with self.assertRaisesRegex(RuntimeError,'entry point'):self.observe(instance,bad)
        with patch.object(guard,'verify_release',return_value={'release_id':'wrong'}):
            with self.assertRaisesRegex(RuntimeError,'self-test release'):self.observe(instance,resumed)

    def test_same_pid_with_new_start_tick_is_a_new_owner(self):
        instance=self.runtime();instance.process['start_ticks']=10
        with patch.object(guard,'verify_release',return_value={'release_id':'audited'}) as verify:
            self.observe(instance,dict(self.process,start_ticks=11));verify.assert_called_once()

    def test_proc_disappearance_is_waiting_not_an_admitted_process(self):
        instance=self.runtime()
        self.assertFalse(self.observe(instance,{'state':'active','pid':0,'read_race':True}))
        self.assertIsNone(instance.acquisition_identity)


class CleanupTests(unittest.TestCase):
    def test_borrowed_overlay_is_not_reprogrammed_on_normal_exit(self):
        lib, overlay, buffer, restore = Mock(), Mock(), Mock(), Mock()
        lib.display_close.return_value = True
        guard.cleanup_display(lib, overlay, True, [buffer], 'eye', restore, restore=False)
        buffer.freebuffer.assert_called_once()
        overlay.download.assert_not_called()
        restore.assert_not_called()

    def test_constructor_failure_after_download_still_restores(self):
        restore = Mock()
        guard.cleanup_display(Mock(), None, False, [], 'original', restore, download_attempted=True)
        restore.assert_called_once_with('original')

    def test_halt_precedes_free_and_restoration(self):
        calls = []
        lib = Mock()
        lib.display_close.side_effect = lambda: calls.append('halt') or True
        buffers = [Mock()]
        buffers[0].freebuffer.side_effect = lambda: calls.append('free')
        guard.cleanup_display(lib, Mock(), True, buffers, 'original', lambda _: calls.append('restore'))
        self.assertEqual(calls, ['halt', 'free', 'restore'])

    def test_failed_halt_requires_reset_before_free(self):
        calls = []
        lib, overlay, buffer = Mock(), Mock(), Mock()
        lib.display_close.return_value = False
        overlay.download.side_effect = lambda: calls.append('reset')
        buffer.freebuffer.side_effect = lambda: calls.append('free')
        guard.cleanup_display(lib, overlay, True, [buffer], 'original', lambda _: calls.append('restore'))
        self.assertEqual(calls, ['reset', 'free', 'restore'])

    def test_failed_reset_never_frees_dma_owned_buffers(self):
        lib, overlay, buffer, restore = Mock(), Mock(), Mock(), Mock()
        lib.display_close.return_value = False
        overlay.download.side_effect = RuntimeError('reset failed')
        with self.assertRaises(RuntimeError):
            guard.cleanup_display(lib, overlay, True, [buffer], 'original', restore)
        buffer.freebuffer.assert_not_called()
        restore.assert_not_called()

    def test_failed_restore_propagates_without_stopping_brain(self):
        lib, overlay, buffer, restore = Mock(), Mock(), Mock(), Mock()
        lib.display_close.return_value = True
        restore.side_effect = RuntimeError('restore failed')
        with self.assertRaises(RuntimeError):
            guard.cleanup_display(lib, overlay, True, [buffer], 'original', restore)
        buffer.freebuffer.assert_called_once()


if __name__ == '__main__':
    unittest.main()

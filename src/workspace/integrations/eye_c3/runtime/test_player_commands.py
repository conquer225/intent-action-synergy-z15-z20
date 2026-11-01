import json
from pathlib import Path
import tempfile
import unittest
from player_commands import PlayerCommands


class InboxTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.inbox=PlayerCommands('test','session',self.tmp.name)

    def put(self, action, stamp, session='session', ident=None):
        lane='stop' if action=='force_stop' else 'command'
        path=Path(self.tmp.name)/('test-player-'+lane+'.json')
        path.write_text(json.dumps(dict(session_id=session,id=ident or action+str(stamp),
                                       action=action,queued_monotonic=stamp)))

    def test_stop_is_not_overwritten_and_pre_stop_navigation_is_discarded(self):
        self.put('arm',10);self.put('force_stop',11)
        self.assertEqual(self.inbox.poll()['action'],'force_stop')
        self.assertEqual(self.inbox.poll(),{})
        self.put('home',12);self.assertEqual(self.inbox.poll()['action'],'home')
        self.assertEqual(self.inbox.poll(),{})

    def test_newer_navigation_cannot_hide_pending_stop(self):
        self.put('force_stop',10);self.put('choose',11)
        self.assertEqual(self.inbox.poll()['action'],'force_stop')
        self.assertEqual(self.inbox.poll()['action'],'choose')

    def test_old_sessions_ignored_and_bad_time_rejected(self):
        self.put('force_stop',10,session='old')
        self.assertEqual(self.inbox.poll(),{})
        self.put('force_stop',float('nan'))
        with self.assertRaises(ValueError):self.inbox.poll()


if __name__=='__main__':unittest.main()

import unittest

from historical_entry import historical_text, reject_wearing_change
from historical_restore import may_restore


class HistoricalEntryTests(unittest.TestCase):
    def test_brain_labels_are_historical_but_eye_and_choices_are_unchanged(self):
        self.assertEqual(historical_text('GuardianLoop'), '历史脑电回放')
        self.assertEqual(historical_text('心情参考 中性情绪'), '历史心情 中性情绪')
        self.assertEqual(historical_text('疲劳 正常'), '历史疲劳 正常')
        for words in ('眼控 selection', '左眼 90%', '上一条', '10 Hz / 后退'):
            self.assertEqual(historical_text(words), words)

    def test_replay_cannot_clear_real_calibration(self):
        for action in ('wear_new', 'wear_continue'):
            with self.assertRaisesRegex(ValueError, '不能修改真实佩戴'):
                reject_wearing_change(object(), action, {'confirm': True, 'expected_id': 'real'})

    def test_static_restore_requires_cleanup_and_unchanged_session_ownership(self):
        report = {'original_restored': True, 'buffers_released': True}
        self.assertTrue(may_restore(report, 'previous', 'previous'))
        self.assertFalse(may_restore(report, 'new-user-session', 'previous'))
        self.assertFalse(may_restore(dict(report, original_restored=False), 'previous', 'previous'))
        self.assertFalse(may_restore(dict(report, buffers_released=False), 'previous', 'previous'))


if __name__ == '__main__':
    unittest.main()

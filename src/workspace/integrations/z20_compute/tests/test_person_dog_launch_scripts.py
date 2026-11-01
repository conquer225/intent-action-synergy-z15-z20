"""Packaged launchers must be readable by the board's Linux shell."""
from pathlib import Path
import tempfile
import unittest

from build_person_dog_two import write_launch_scripts


class PersonDogLaunchScriptsTests(unittest.TestCase):
    def test_linux_launchers_have_lf_lines_and_forward_options(self):
        with tempfile.TemporaryDirectory() as directory:
            write_launch_scripts(Path(directory))
            for mode in ('video', 'photos', 'diagnostic'):
                data = (Path(directory) / ('run_' + mode + '.sh')).read_bytes()
                self.assertNotIn(b'\r', data)
                self.assertTrue(data.startswith(b'#!/bin/sh\nset -eu\n'))
                self.assertIn(b'cd "$(dirname "$0")"\n', data)
                self.assertTrue(data.endswith(
                    ('--mode ' + mode + ' --hdmi "$@"\n').encode('ascii')))


if __name__ == '__main__':
    unittest.main()

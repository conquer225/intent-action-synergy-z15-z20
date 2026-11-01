"""Native adapter path handling at the external shared-library loader."""
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from z20_compute.native_person_dog import NativeMedia


class NativeMediaTests(unittest.TestCase):
    def test_relative_library_path_loads_from_the_working_directory(self):
        def loader(name):
            # ELF dlopen does not search the working directory for a bare name.
            if not Path(name).is_absolute():
                raise OSError('bare library name is not found in loader search paths')
            return Mock()

        with patch('z20_compute.native_person_dog.C.CDLL', side_effect=loader):
            media = NativeMedia(Path('libperson_dog.so'))
            media.close()


if __name__ == '__main__':
    unittest.main()

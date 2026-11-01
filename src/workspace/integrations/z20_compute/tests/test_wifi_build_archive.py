import io
import tarfile
import unittest


class BuildArchiveTests(unittest.TestCase):
    def test_native_environment_relocates_perl_modules_with_the_tools(self):
        from hardware.linux.build_wifi_native import native_environment
        from pathlib import PurePosixPath
        environment=native_environment(PurePosixPath('/private/native'),{'PATH':'/bin'})
        self.assertIn('/private/native/usr/share/perl/5.28.1',environment['PERL5LIB'].split(':'))
        self.assertIn('/private/native/usr/lib/arm-linux-gnueabihf/perl/5.28',environment['PERL5LIB'].split(':'))
        self.assertEqual(environment['M4'],'/private/native/usr/bin/m4')

    def test_private_perl_can_use_libcrypt_without_replacing_board_glibc(self):
        from hardware.linux.build_wifi_native import is_board_runtime_library
        self.assertFalse(is_board_runtime_library('libcrypt.so.1'))
        self.assertFalse(is_board_runtime_library('libcrypt-2.28.so'))
        for name in ('libc.so.6','libm-2.28.so','ld-linux-armhf.so.3','libpthread.so.0'):
            self.assertTrue(is_board_runtime_library(name))

    def test_native_library_dependencies_include_transitive_runtime_libraries(self):
        from prepare_wifi_build import library_dependencies
        records={'m4':{'Depends':'libsigsegv2 (>= 2.9), libc6 | libc6.1'},
                 'libsigsegv2':{'Depends':'libgcc1:any'},'libgcc1':{},'libc6':{}}
        self.assertEqual(set(library_dependencies(records,['m4'])),
                         {'m4','libsigsegv2','libgcc1','libc6'})

    def test_private_prefix_applies_to_hard_link_targets(self):
        from prepare_wifi_build import append_data_tar
        source=io.BytesIO()
        with tarfile.open(fileobj=source,mode='w') as archive:
            item=tarfile.TarInfo('./usr/bin/original');item.size=4
            archive.addfile(item,io.BytesIO(b'test'))
            link=tarfile.TarInfo('./usr/bin/alias');link.type=tarfile.LNKTYPE
            link.linkname='./usr/bin/original';archive.addfile(link)
        output=io.BytesIO()
        with tarfile.open(fileobj=output,mode='w') as archive:append_data_tar(archive,source.getvalue())
        with tarfile.open(fileobj=io.BytesIO(output.getvalue()),mode='r') as archive:
            self.assertEqual(archive.getmember('native/usr/bin/alias').linkname,'native/usr/bin/original')
            self.assertEqual(archive.extractfile('native/usr/bin/alias').read(),b'test')


if __name__=='__main__':unittest.main()

"""Build inside a private board directory; never installs or loads a module."""
import argparse
import gzip
import hashlib
import json
import os
import re
from pathlib import Path
import shutil
import subprocess
import tarfile
import time
import urllib.request


def is_board_runtime_library(name):
    # Debian Perl needs libcrypt.so.1; it is not the board's loader or libc.
    return re.match(r'^(libc[-.]|libm[-.]|libpthread|libdl|librt|libresolv|libnss_|libanl|libBrokenLocale|libutil|ld-)',name) is not None


def native_environment(native,base):
    return dict(base,
        PATH=str(native/'usr/bin')+':'+base.get('PATH','/bin:/usr/bin'),
        LD_LIBRARY_PATH=str(native/'usr/lib/arm-linux-gnueabihf')+':'+str(native/'tool-libs'),
        M4=str(native/'usr/bin/m4'),BISON_PKGDATADIR=str(native/'usr/share/bison'),
        PERL5LIB=':'.join(str(native/name) for name in (
            'usr/share/perl/5.28.1','usr/share/perl/5.28',
            'usr/lib/arm-linux-gnueabihf/perl/5.28.1','usr/lib/arm-linux-gnueabihf/perl/5.28',
            'usr/lib/arm-linux-gnueabihf/perl-base')))


def extract(archive, destination):
    root=destination.resolve()
    with tarfile.open(archive,'r:gz') as source:
        for entry in source:
            parts=Path(entry.name).parts
            if entry.name.startswith('/') or '..' in parts or entry.isdev():
                raise ValueError('unsafe build archive member')
            parent=(root/entry.name).parent.resolve()
            if parent!=root and root not in parent.parents:
                raise ValueError('build archive ancestor escapes workspace')
            source.extract(entry,str(root))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,required=True)
    parser.add_argument('--server',required=True)
    parser.add_argument('--resume',action='store_true')
    args=parser.parse_args()
    root=args.root.resolve()
    previously_extracted={}
    if args.resume:
        previous=json.loads((root/'build.json').read_text())
        if previous.get('scope')!='private native build only; existing kernel/PL unchanged':
            raise ValueError('unrecognized build workspace')
        if previous.get('pid'):
            try:os.kill(previous['pid'],0)
            except ProcessLookupError:pass
            else:raise RuntimeError('previous build process still exists')
        if previous.get('commands') and (root/'sources.json').is_file():
            old=json.loads((root/'sources.json').read_text())
            previously_extracted={row['file']:row['sha256'] for row in old['sources']}
            previously_extracted['native-build-tools.tar.gz']=old['native_tools_sha256']
    root.mkdir(parents=True,exist_ok=args.resume)
    report=dict(started_unix=time.time(),scope='private native build only; existing kernel/PL unchanged',
                passed=False,stage='download',pid=os.getpid(),commands=[])
    def save():
        (root/'build.json').write_text(json.dumps(report,indent=2))
    def run(command,cwd,environment):
        print('RUN '+repr(command),flush=True)
        started=time.time()
        result=subprocess.run(command,cwd=str(cwd),env=environment)
        report['commands'].append(dict(argv=command,exit_code=result.returncode,seconds=time.time()-started))
        save()
        if result.returncode:raise RuntimeError('build command failed')
    try:
        with urllib.request.urlopen(args.server+'/sources.json',timeout=30) as response:
            manifest=json.load(response)
        expected={r['file']:r['sha256'] for r in manifest['sources']}
        expected['native-build-tools.tar.gz']=manifest['native_tools_sha256']
        for name in ('native-build-tools.tar.gz','linux-xilinx-v2020.2.tar.gz','rtl8733bu.tar.gz'):
            path=root/name
            cached=path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest()==expected[name]
            if not cached:
                with urllib.request.urlopen(args.server+'/'+name,timeout=60) as response,path.open('wb') as output:
                    shutil.copyfileobj(response,output,1024*1024)
            digest=hashlib.sha256(path.read_bytes()).hexdigest()
            if digest!=expected[name]:raise ValueError('build archive hash mismatch')
            print('VERIFIED '+name,flush=True)
            stamp=root/(name+'.extracted.sha256')
            extracted=stamp.is_file() and stamp.read_text()==digest
            if not extracted and previously_extracted.get(name)!=digest:extract(path,root)
            stamp.write_text(digest)
        (root/'sources.json').write_text(json.dumps(manifest,indent=2))
        native=root/'native'
        for name in ('gcc','arm-linux-gnueabihf-gcc'):
            link=native/'usr/bin'/name
            if not link.exists():link.symlink_to('arm-linux-gnueabihf-gcc-8')
        libraries=native/'tool-libs';libraries.mkdir(exist_ok=True)
        for path in (native/'lib/arm-linux-gnueabihf').glob('*.so*'):
            # Use the board's own loader/glibc. Other build-tool libraries stay private.
            if is_board_runtime_library(path.name):continue
            target=libraries/path.name
            if not target.exists():target.symlink_to(path)
        environment=native_environment(native,os.environ)
        compiler=str(native/'usr/bin/gcc')+' --sysroot='+str(native)
        (root/'hello.c').write_text('#include <stdio.h>\nint main(void){puts("PRIVATE_ARM_GCC_OK");return 0;}\n')
        run([str(native/'usr/bin/gcc'),'--sysroot='+str(native),str(root/'hello.c'),'-o',str(root/'hello')],root,environment)
        run([str(root/'hello')],root,environment)
        kernel=root/'linux-xlnx-xilinx-v2020.2'
        (kernel/'.config').write_bytes(gzip.decompress(Path('/proc/config.gz').read_bytes()))
        make=[str(native/'usr/bin/make'),'ARCH=arm','CC='+compiler,'HOSTCC='+compiler]
        report['stage']='kernel_prepare';save()
        run(make+['olddefconfig','prepare','modules_prepare'],kernel,environment)
        release=subprocess.check_output(make+['-s','kernelrelease'],cwd=str(kernel),env=environment).decode().strip()
        report['built_kernel_release']=release
        if release!=os.uname().release:raise ValueError('kernel release differs from running target')
        # MODVERSIONS requires an actual kernel symbol table, not an empty stub.
        report['stage']='kernel_build';save()
        run(make+['-j2','zImage','modules'],kernel,environment)
        driver=next(p for p in root.glob('rtl8733bu-*') if p.is_dir())
        report['stage']='driver_build';save()
        run([str(native/'usr/bin/make'),'-j2','ARCH=arm','CC='+compiler,'HOSTCC='+compiler,
             'CROSS_COMPILE=arm-linux-gnueabihf-','KSRC='+str(kernel),'modules'],driver,environment)
        module=driver/'8733bu.ko'
        if not module.is_file():raise ValueError('built module missing')
        report.update(passed=True,stage='built_not_loaded',module=str(module),
                      module_sha256=hashlib.sha256(module.read_bytes()).hexdigest())
    except BaseException as exc:
        report['error']=type(exc).__name__+': '+str(exc)
        raise
    finally:save()


if __name__=='__main__':main()

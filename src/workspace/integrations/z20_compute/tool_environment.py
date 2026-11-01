"""Local Windows tool bootstrap for hosts whose DLL search omits PATH.

Installation files remain read-only. Hard links (or copies across volumes) live
under this module's ignored build directory; never write into a linked file.
"""
import os
from pathlib import Path
import runpy
import shutil
import subprocess
import struct

HERE = Path(__file__).resolve().parent


def link_file(source, target):
    if target.exists():
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.link(source, target)
    except OSError:
        shutil.copy2(source, target)


def directory_link(source,target):
    """Keep a private directory alias; never replace an existing unrelated path."""
    target=target.absolute();target.relative_to((HERE/'build').resolve())
    if target.exists():
        if not os.path.samefile(source,target):raise ValueError('Tool directory alias differs: '+str(target))
        return
    target.parent.mkdir(parents=True,exist_ok=True)
    subprocess.run([str(Path(os.environ['SYSTEMROOT'])/'System32/cmd.exe'),'/d','/c',
                    'mklink','/J',str(target),str(source)],check=True,capture_output=True)


def prepare_arm_compiler(vitis_root):
    """Keep GCC's relative layout and supply local runtime DLLs in a workspace copy."""
    source = Path(vitis_root)/"gnu/aarch32/nt/gcc-arm-none-eabi"
    environment = os.environ.copy()
    for key in ("LANG", "LC_ALL", "LC_CTYPE"):
        environment[key] = "C"
    if os.name != "nt":
        return source/"bin/arm-none-eabi-gcc", environment
    target = HERE/"build/arm-baremetal"
    executable_dirs = set()
    for path in source.rglob("*"):
        if path.is_file():
            copied = target/path.relative_to(source)
            link_file(path, copied)
            if path.suffix.lower() == ".exe":
                executable_dirs.add(copied.parent)
    runtime = list((source/"x86_64-oesdk-mingw32/usr/bin").glob("*.dll"))
    for directory in executable_dirs:
        for library in runtime:
            link_file(library, directory/library.name)
    return target/"bin/arm-none-eabi-gcc.exe", environment


def virtual_hls(root):
    """Mirror executable directories, junction static data; keep tool files intact."""
    virtual = HERE/"build/toolchain/Vitis_HLS"/root.name
    executable_dirs = [Path(p) for p in ("bin/unwrapped/win64.o", "win64/tools/clang-3.9-csynth/bin",
            "win64/tools/auto_cc/bin", "win64/tools/clang/bin", "tps/win64/msys64/mingw64/bin",
            "tps/win64/msys64/mingw64/lib/gcc/x86_64-w64-mingw32/6.2.0")]
    def mirror(relative=Path()):
        target = virtual/relative
        target.mkdir(parents=True, exist_ok=True)
        for source in (root/relative).iterdir():
            rel = source.relative_to(root)
            dest = virtual/rel
            if source.is_file():
                link_file(source, dest)
            elif any(rel == needed or rel in needed.parents for needed in executable_dirs):
                mirror(rel)
            elif not dest.exists():
                subprocess.run([str(Path(os.environ["SYSTEMROOT"])/"System32/cmd.exe"),
                                "/d", "/c", "mklink", "/J", str(dest), str(source)],
                               check=True, capture_output=True)
    mirror()
    dlls = list((root/"lib/win64.o").glob("*.dll"))
    dlls += list((root/"tps/win64").glob("jre*/bin/*.dll"))
    dlls += list((root/"tps/win64").glob("jre*/bin/server/*.dll"))
    dlls += list((root/"tps/win64/msys64/mingw64/bin").glob("*.dll"))
    for relative in executable_dirs:
        if (virtual/relative).is_dir():
            for dll in dlls:
                link_file(dll, virtual/relative/dll.name)
    return virtual


def prepare(root):
    root = Path(root).resolve()
    environment = runpy.run_path(str(HERE.parent/"vision_demo/build_hls.py"))["environment"](root)
    if os.name != "nt":
        return root/"bin/vitis_hls", environment
    if root.parent.name == "Vitis_HLS":
        virtual = virtual_hls(root)
        environment = runpy.run_path(str(HERE.parent/"vision_demo/build_hls.py"))["environment"](virtual)
        environment["XILINX_VIVADO"] = (root.parents[1]/"Vivado"/root.name).as_posix()
        environment["RDI_INSTALLROOT"] = root.parents[1].as_posix()
        environment["RDI_DATADIR"] = virtual.as_posix()+"/data;"+environment["XILINX_VIVADO"]+"/data"
        environment["AP_GCC_PATH"] = (virtual/"tps/win64/msys64/mingw64/bin").as_posix()
        return virtual/"bin/unwrapped/win64.o/vitis_hls.exe", environment
    bootstrap = HERE/"build"/(root.parent.name.lower()+"-bootstrap")
    bootstrap.mkdir(parents=True, exist_ok=True)
    sources = list((root/"lib/win64.o").glob("*.dll"))
    sources += list((root/"bin/unwrapped/win64.o").glob("*.exe"))
    sources += list((root/"tps/win64").glob("jre*/bin/*.dll"))
    sources += list((root/"tps/win64").glob("jre*/bin/server/*.dll"))
    if root.parent.name == "Vivado":
        for source in (root/"tps/win64").rglob("*.dll"):
            with source.open("rb") as stream:
                stream.seek(0x3c)
                offset = struct.unpack("<I", stream.read(4))[0]
                stream.seek(offset+4)
                if stream.read(2) == b"\x64\x86":
                    sources.append(source)
    for source in sources:
        link_file(source, bootstrap/source.name)
    environment["RDI_BINDIR"] = bootstrap.as_posix()
    if root.parent.name=='Vivado':
        # Srcscanner is derived from RDI_LIBDIR/../../bin/unwrapped/win64.o,
        # not RDI_BINDIR. Preserve that layout so the child can load its DLLs.
        runtime=HERE/'build/vivado-runtime'/root.name
        directory_link(root/'lib/win64.o',runtime/'lib/win64.o')
        directory_link(bootstrap,runtime/'bin/unwrapped/win64.o')
        environment['RDI_LIBDIR']=(runtime/'lib/win64.o').as_posix()
    return bootstrap/("vivado.exe" if root.parent.name == "Vivado" else "vitis_hls.exe"), environment

"""Build a standalone stereo bring-up BOOT from supplied vendor sources and new XSA.

No board writes. Vendor sources and tool installation remain unchanged.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import zipfile
import struct

HERE = Path(__file__).resolve().parent


def build(args):
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    commands = []
    from tool_environment import prepare_arm_compiler
    gcc, compiler_environment = prepare_arm_compiler(args.vitis_root)

    def run(command, cwd=out, env=None):
        p = subprocess.run(list(map(str, command)), cwd=cwd,
                           env=compiler_environment if env is None else env, capture_output=True,
                           text=True, encoding='utf-8', errors='replace', timeout=120)
        commands.append(dict(command=list(map(str, command)), exit_code=p.returncode,
                             stdout=p.stdout, stderr=p.stderr))
        (out/'commands.json').write_text(json.dumps(commands, indent=2), encoding='utf-8')
        if p.returncode:
            raise RuntimeError(p.stderr or p.stdout or f'tool exited {p.returncode}')
        return p.stdout

    sysroot = args.vitis_root/'gnu/aarch32/nt/gcc-arm-none-eabi/aarch32-xilinx-eabi'
    flags = ['-mcpu=cortex-a9', '-mfpu=vfpv3', '-mfloat-abi=hard',
             '--sysroot='+str(sysroot), '-O2', '-fcommon', '-ffunction-sections', '-fdata-sections']
    if args.uboot:
        raw = args.uboot.read_bytes()
        if raw[:6] != b'\x7fELF\x01\x01' or struct.unpack_from('<H', raw, 18)[0] != 40:
            raise ValueError('U-Boot must be a little-endian ARM ELF32')
        entry = struct.unpack_from('<I', raw, 24)[0]
        if entry != 0x04000000:
            raise ValueError('supplied U-Boot entry does not match audited 64 MiB address')
        flags.append('-DZ20_UBOOT_ENTRY=0x04000000u')
    appsrc = args.official/'vitis/dual_ov5640_hdmi/src'
    bsp = args.official/'vitis/system_wrapper/export/system_wrapper/sw/system_wrapper/standalone_ps7_cortexa9_0'
    fsbl = args.official/'vitis/system_wrapper/zynq_fsbl'
    fsrc = out/'fsbl-source'
    fsrc.mkdir(exist_ok=True)
    for p in fsbl.iterdir():
        if p.is_file() and (p.suffix in ('.c', '.h', '.S') or p.name in ('lscript.ld', 'Xilinx.spec')):
            shutil.copyfile(p, fsrc/p.name)
    with zipfile.ZipFile(args.xsa) as z:
        if z.testzip() is not None: raise ValueError('XSA CRC failed')
        for name in ('ps7_init.c', 'ps7_init.h'):
            (fsrc/name).write_bytes(z.read(name))

    def compile_link(name, sources, includes, library, script, extra_libs):
        directory = out/name
        directory.mkdir(exist_ok=True)
        objects = []
        for i, source in enumerate(sources):
            obj = directory/(str(i)+'-'+source.stem+'.o')
            run([gcc, *flags, *['-I'+str(p) for p in includes], '-c', source, '-o', obj])
            objects.append(obj)
        spec = appsrc/'Xilinx.spec'
        elf = out/(name+'.elf')
        run([gcc, *flags, '-specs='+str(spec), '-Wl,-T,'+str(script),
             '-Wl,-Map,'+str(out/(name+'.map')), '-Wl,--gc-sections',
             '-L'+str(library), *objects, '-Wl,--start-group',
             *extra_libs, '-lxil', '-lgcc', '-lc', '-Wl,--end-group', '-o', elf])
        return elf

    sources = [HERE/'hardware/standalone/main.c', HERE/'hardware/standalone/video_boot.c']
    sources += [appsrc/f for f in ('display_ctrl_hdmi/display_ctrl_hdmi.c',
                'emio_sccb_cfg/emio_sccb_cfg.c', 'ov5640/ov5640_init.c')]
    if args.uboot: sources.append(fsrc/'fsbl_handoff.S')
    app = compile_link('dual_video', sources,
                       [HERE/'hardware/standalone', appsrc, bsp/'bspinclude/include'],
                       bsp/'bsplib/lib', appsrc/'lscript.ld', [])
    fsbl_elf = compile_link('fsbl', sorted(fsrc.glob('*.c'))+sorted(fsrc.glob('*.S')),
                           [fsrc, fsbl/'zynq_fsbl_bsp/ps7_cortexa9_0/include'],
                           fsbl/'zynq_fsbl_bsp/ps7_cortexa9_0/lib', fsrc/'lscript.ld',
                           ['-lrsa', '-lxilffs'])
    bit = out/'system.bit'
    shutil.copyfile(args.bit, bit)
    bif = out/'boot.bif'
    bif.write_text('the_ROM_image:\n{\n [bootloader] '+fsbl_elf.as_posix()+'\n '+
                   bit.as_posix()+'\n '+app.as_posix()+'\n '+
                   (args.uboot.resolve().as_posix()+'\n' if args.uboot else '')+'}\n')
    from tool_environment import prepare
    executable, environment = prepare(args.vitis_root.parents[1]/'Vivado'/args.vitis_root.name)
    bootgen = executable.parent/'bootgen.exe'
    run([bootgen, '-arch', 'zynq', '-image', bif, '-o', out/'BOOT.BIN', '-w', 'on'], env=environment)
    run([bootgen, '-arch', 'zynq', '-read', out/'BOOT.BIN'], env=environment)
    inputs = set(sources) | set(fsrc.glob('*'))
    inputs.update(p for p in bsp.rglob('*') if p.is_file())
    inputs.update(p for p in (fsbl/'zynq_fsbl_bsp').rglob('*') if p.is_file())
    inputs.update([gcc, args.xsa, args.bit, appsrc/'Xilinx.spec', appsrc/'lscript.ld'])
    if args.uboot: inputs.add(args.uboot)
    result = dict(kind='stereo-linux-handoff' if args.uboot else 'standalone-stereo-bringup', built=True, board_executed=False,
                  linux_image=False, linux_handoff=bool(args.uboot),
                  compiler_version=run([gcc, '--version']).splitlines()[0],
                  inputs={p.as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(inputs) if p.is_file()},
                  matched_xsa_sha256=hashlib.sha256(args.xsa.read_bytes()).hexdigest(),
                  files={p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                         for p in (app, fsbl_elf, bit, bif, out/'BOOT.BIN')})
    (out/'manifest.json').write_text(json.dumps(result, indent=2))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--vitis-root', type=Path, default=Path('D:/vivado/Vitis/2023.1'))
    parser.add_argument('--official', type=Path, default=HERE/'build/official_z20_vitis/37_dual_ov5640_hdmi')
    parser.add_argument('--xsa', type=Path, default=HERE/'build/implementation/z20_video_npu_hardware.xsa')
    parser.add_argument('--bit', type=Path, default=HERE/'build/implementation/z20_video_npu_candidate.bit')
    parser.add_argument('--output', type=Path, default=HERE/'build/stereo_boot')
    parser.add_argument('--uboot', type=Path, help='optional audited vendor U-Boot ELF; video initializes before handoff')
    result = build(parser.parse_args())
    print(json.dumps({key:value for key,value in result.items() if key != 'inputs'}, indent=2))

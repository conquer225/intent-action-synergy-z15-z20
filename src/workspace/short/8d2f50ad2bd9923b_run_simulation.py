"""Run isolated HDL simulation; no synthesis or board access."""
import argparse
import hashlib
import json
import re
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
BIN = Path('D:/ruanjian/2025.2/Vivado/bin')
SERIALIZER = Path('D:/ican/【正点原子】Z15 ZYNQ7015开发板资料盘（A盘）/4_Source_Code/3_Embedded_Linux/vivado_prj/Z15_ZYNQ/ip_repo/DVI_TX/ip/src/serializer_10_to_1.v')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--suite', choices=['pcm', 'pcm_ticks', 'pcm_capacity', 'packets', 'video', 'serial', 'status'], default='pcm')
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    if args.suite in ('pcm', 'pcm_ticks', 'pcm_capacity'):
        sources = [HERE/'rtl/pcm_buffer.sv', HERE/'sim/pcm_buffer_tb.sv']
        top = dict(pcm='pcm_buffer_tb',pcm_ticks='pcm_ticks_tb',pcm_capacity='pcm_capacity_tb')[args.suite]
        marker = 'PCM_BUFFER_PASS'
    elif args.suite == 'serial':
        sources = [SERIALIZER, HERE/'sim/serializer_tb.sv']
        top, marker = 'serializer_tb', 'SERIALIZER_PASS'
    elif args.suite == 'status':
        sources = [HERE/'rtl/display_status.sv', HERE/'sim/display_status_tb.sv']
        top, marker = 'display_status_tb', 'DISPLAY_STATUS_PASS'
    else:
        upstream = HERE/'third_party/hdmi/src'
        names = ['packet_picker', 'packet_assembler', 'audio_clock_regeneration_packet',
                 'audio_sample_packet', 'audio_info_frame',
                 'auxiliary_video_information_info_frame', 'source_product_description_info_frame']
        sources = [HERE/'rtl/audio_sample_clock.sv', HERE/'rtl/audio_sample_tick.sv', HERE/'sim/audio_packets_tb.sv',
                   *(upstream/(name+'.sv') for name in names)]
        top, marker = 'audio_packets_tb', 'AUDIO_PACKETS_PASS'
        if args.suite == 'video':
            sources += [HERE/'rtl/hdmi_external_video.sv', upstream/'tmds_channel.sv']
            top = 'hdmi_external_tb'
    snapshot = top+'_sim'
    source_hashes = {str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}
    commands = [('xvlog.bat', ['--sv', '-d', 'MODEL_TECH', *map(str,sources), str(BIN.parent/'data/verilog/src/glbl.v')]),
                ('xelab.bat', [top, 'glbl', '--timescale', '1ns/1fs', '-L', 'xpm', '-L', 'unisims_ver', '-L', 'secureip', '-s', snapshot]),
                ('xsim.bat', [snapshot, '-runall'])]
    for name, arguments in commands:
        r = subprocess.run([str(BIN/name), *arguments], cwd=out,
                           capture_output=True, text=True, timeout=180)
        log = r.stdout+r.stderr
        (out/(name+'.txt')).write_text(log,encoding='utf-8')
        print('\n'.join(log.splitlines()[-70:]),flush=True)
        if r.returncode or re.search(r'(?im)^(error:|fatal:)', log):
            raise RuntimeError(name+' failed')
    if marker not in log:
        raise RuntimeError('Simulation ended without full pass marker')
    if source_hashes != {str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}:
        raise RuntimeError('Source changed during simulation; rerun the final revision')
    (out/'result.json').write_text(json.dumps(dict(passed=True, scope=args.suite+' RTL only; no HDMI/audio hardware claim',
        sources=source_hashes),indent=2))


if __name__ == '__main__':
    main()

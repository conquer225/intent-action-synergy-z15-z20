"""Collect reports and artifact hashes, not private screen/video contents or keys."""
import json
from pathlib import Path
import shlex

import stage_server as upload
from stage_media import STATE


def main():
    state=json.loads(STATE.read_text());c=upload.trial.connect('192.168.2.99')
    output=Path(__file__).resolve().parent/'output/long_cache_20261007'
    try:
        with c.open_sftp() as sftp:
            for name in sftp.listdir(state['remote']):
                if name.startswith('play-') and name.endswith('-report.json'):
                    sftp.get(state['remote']+'/'+name,str(output/name))
            for folder in ('fixture60preview','fixture60compact','eeg-video-load','eeg-load-current','eeg-compact-load'):
                destination=output/folder;destination.mkdir(exist_ok=True)
                for name in sftp.listdir(state['remote']+'/'+folder):
                    if name.endswith(('.json','.jsonl','.log')):
                        sftp.get(state['remote']+'/'+folder+'/'+name,str(destination/name))
            for name in ('neon_audit.json','expander_audit.json','board_tests.log'):
                if name in sftp.listdir(state['remote']):
                    sftp.get(state['remote']+'/'+name,str(output/name))
        manifest=json.loads(upload.trial.execute(c,'cat /home/xilinx/jupyter_notebooks/guardianloop_pynq/release_manifest.json'))
        files=manifest['files']
        command='sha256sum '+' '.join(shlex.quote('/home/xilinx/jupyter_notebooks/guardianloop_pynq/'+name) for name in files)
        text=upload.trial.execute(c,command,root=True)
        actual={line.split()[1].rsplit('/',1)[-1]:line.split()[0] for line in text.splitlines()}
        after=upload.trial.protected(c)
        services=upload.trial.services(c)
        pl=upload.trial.execute(c,'env XILINX_XRT=/usr /usr/local/share/pynq-venv/bin/python3 -c '+
            shlex.quote('from pynq import PL; print(PL.bitfile_name)'),root=True).strip()
        boot=upload.trial.execute(c,'cat /proc/sys/kernel/random/boot_id').strip()
        prior_boots={json.loads(path.read_text()).get('admission',{}).get('boot_id')
                     for path in output.glob('play-*-report.json')}
        prior_boots.discard(None)
        original_sha=upload.trial.execute(c,'sha256sum '+shlex.quote(
            state['uploaded_root']+'/d87609d9be1c4738ba9dc378438d9935.mp4')).split()[0]
        audit=dict(release_id=manifest['release_id'],release_files_verified=len(files),
            release_unchanged=actual==files,protected_unchanged=after==state['before_hashes'],
            before_services=state['before_services'],after_services=services,pl=pl,
            pl_restored=pl==state['original_overlay'],audio_output=False,physical_control=False,
            boot_unchanged=prior_boots=={boot},original_video_sha256=original_sha,
            original_video_unchanged=original_sha=='3fe1eacc6f3472327359dcb667e44fea59f099b5dd1e223eded48efccca43434',
            scope='Private caches, old recorded EEG, USB eye diagnostic only; no new accuracy result')
        (output/'final_audit.json').write_text(json.dumps(audit,indent=2),encoding='utf-8')
        print(json.dumps(audit,ensure_ascii=False),flush=True)
        for path in output.glob('play-*-report.json'):
            report=json.loads(path.read_text())
            keys=('fps','frames','wall_s','minimum_full_second_frames','meets_16fps',
                  'buffering_events','cache_ram_mib','eof_reached','errors','original_restored')
            print(json.dumps(dict(session=path.stem,**{k:report.get(k) for k in keys}),ensure_ascii=False))
    finally:c.close()


if __name__=='__main__':main()

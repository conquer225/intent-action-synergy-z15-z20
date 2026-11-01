"""Test final diagnostics/recovery candidate without touching the ongoing soak or USB."""
import hashlib
import json
from pathlib import Path
import shlex
from eeg_apps_z15.run_soak_stage import ROOT, OUT, connect, command


def main():
    m=json.loads((OUT/'manifest.json').read_text())
    stage=m['stage']+'/candidate'
    c=connect()
    command(c,'mkdir '+stage)
    files=list(m['protected'])
    files+=['test_small_batch.py','test_seed_shadow.py','test_seed_reader_timing.py',
            'test_seed_quality_runtime.py','test_seed_shadow_web.py','profile_service_replay.py','verify_stream_recovery.py']
    hashes={}
    with c.open_sftp() as s:
        for name in files:
            local=ROOT/'pynq_guardianloop'/name
            if not local.is_file():local=OUT/'original'/name
            s.put(str(local),stage+'/'+name)
            hashes[name]=hashlib.sha256(local.read_bytes()).hexdigest()
        s.put(str(ROOT/'eeg_apps_z15/output/board_pipeline_profile_20260926/input.npz'),stage+'/input.npz')
    record={'stage':stage,'hashes':hashes}
    (OUT/'candidate_manifest.json').write_text(json.dumps(record,indent=2))
    shell='cd '+stage+' && export OPENBLAS_NUM_THREADS=1 XILINX_XRT=/usr && '+ \
        'nice -n 10 /usr/local/share/pynq-venv/bin/python3 -m unittest test_small_batch test_seed_shadow test_seed_reader_timing test_seed_quality_runtime test_seed_shadow_web > tests.txt 2>&1 && '+ \
        'nice -n 10 /usr/local/share/pynq-venv/bin/python3 profile_service_replay.py --input input.npz --output parity > parity-launcher.log 2>&1 && '+ \
        'nice -n 10 /usr/local/share/pynq-venv/bin/python3 verify_stream_recovery.py --input input.npz --output faults > fault-launcher.log 2>&1'
    record['pid']=command(c,'nohup sh -c '+shlex.quote(shell)+' > '+stage+'/launcher.log 2>&1 < /dev/null & echo $!').strip()
    (OUT/'candidate_manifest.json').write_text(json.dumps(record,indent=2))
    print(json.dumps(record,indent=2));c.close()


if __name__=='__main__':main()

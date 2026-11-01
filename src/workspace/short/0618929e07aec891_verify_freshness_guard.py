"""Finalize the queue-age guard; wait for existing soak before paced acceptance."""
import hashlib
import json
import shlex
from eeg_apps_z15.run_soak_stage import ROOT,OUT,connect,command


def main():
    m=json.loads((OUT/'candidate_manifest.json').read_text())
    base=json.loads((OUT/'manifest.json').read_text())
    c=connect()
    m['recovery_version_hashes']=dict(m['hashes'])
    with c.open_sftp() as s:
        for name in ('cyton_guardianloop.py','guardianloop_web.py','test_small_batch.py','test_seed_shadow_web.py'):
            local=ROOT/'pynq_guardianloop'/name
            s.put(str(local),m['stage']+'/'+name)
            m['hashes'][name]=hashlib.sha256(local.read_bytes()).hexdigest()
    launch='cd '+m['stage']+' && export OPENBLAS_NUM_THREADS=1 XILINX_XRT=/usr && '+ \
        'while ! test -f '+base['stage']+'/soak/report.json; do sleep 10; done; '+ \
        'cp final-tests.txt recovery-tests.txt && '+ \
        '/usr/local/share/pynq-venv/bin/python3 -m unittest test_small_batch test_seed_shadow test_seed_reader_timing test_seed_quality_runtime test_seed_shadow_web > final-tests.txt 2>&1 && '+ \
        '/usr/local/share/pynq-venv/bin/python3 soak_service_replay.py --input input.npz --output freshness_soak --seconds 60 > freshness-soak.log 2>&1'
    m['freshness_pid']=command(c,'nohup sh -c '+shlex.quote(launch)+' > '+m['stage']+'/freshness-launcher.log 2>&1 < /dev/null & echo $!').strip()
    (OUT/'candidate_manifest.json').write_text(json.dumps(m,indent=2))
    print(m['freshness_pid']);c.close()


if __name__=='__main__':main()

"""Repair only the isolated test harness; preserve its interrupted artifacts."""
import hashlib
import json
import shlex
from eeg_apps_z15.run_soak_stage import ROOT,OUT,connect,command


def main():
    m=json.loads((OUT/'candidate_manifest.json').read_text())
    c=connect()
    for pid in (26844,26948):
        cmdline=command(c,'cat /proc/%d/cmdline'%pid)
        assert 'verify_stream_recovery.py\x00' in cmdline
    command(c,'kill -KILL 26844 26948')
    with c.open_sftp() as s:
        for name in ('verify_stream_recovery.py','guardianloop_web.py','test_small_batch.py','soak_service_replay.py'):
            path=ROOT/'pynq_guardianloop'/name
            s.put(str(path),m['stage']+'/'+name)
            m['hashes'][name]=hashlib.sha256(path.read_bytes()).hexdigest()
    m['fault_dir']='faults_fixed'
    m['harness_repair']='Initial fault generator repeatedly decompressed sequence array; cached once. Interrupted test outputs retained in faults/; no production change.'
    launch='cd '+m['stage']+' && export OPENBLAS_NUM_THREADS=1 XILINX_XRT=/usr && '+ \
        'nice -n 10 /usr/local/share/pynq-venv/bin/python3 verify_stream_recovery.py --input input.npz --output faults_fixed > fault-fixed.log 2>&1 && '+ \
        'nice -n 10 /usr/local/share/pynq-venv/bin/python3 -m unittest test_small_batch test_seed_shadow test_seed_reader_timing test_seed_quality_runtime test_seed_shadow_web > final-tests.txt 2>&1 && '+ \
        '/usr/local/share/pynq-venv/bin/python3 soak_service_replay.py --input input.npz --output final_soak --seconds 300 > final-soak-launcher.log 2>&1'
    m['final_pid']=command(c,'nohup sh -c '+shlex.quote(launch)+' > '+m['stage']+'/final-launcher.log 2>&1 < /dev/null & echo $!').strip()
    (OUT/'candidate_manifest.json').write_text(json.dumps(m,indent=2))
    print(m['final_pid']);c.close()


if __name__=='__main__':main()

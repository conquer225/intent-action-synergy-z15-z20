"""Virtual main-loop silence and resume; no USB, PL, or live status writes."""
import contextlib
import io
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch


@unittest.skipUnless(os.name=='posix','Main service uses Linux serial APIs')
class WaitServiceTests(unittest.TestCase):
    def test_probes_are_bounded_and_resumption_resets_primary(self):
        import numpy as np
        import cyton_guardianloop as live
        from cyton_trial_recorder import TrialRecorder
        with tempfile.TemporaryDirectory() as text:
            root=Path(text);clock=[0.];results=[];configuration=Mock();commands=Mock();opens=[0]
            recorder=TrialRecorder(live.DEFAULT_CHANNEL_MAP,live.DEFAULT_UV_PER_COUNT,
                control_path=root/'command',status_path=root/'recorder',record_root=root/'raw')
            def frames(fd,timeout,with_timing=False,on_idle=None,**options):
                self.assertTrue(options['wait_for_data'])
                opens[0]+=1
                if opens[0]==1:
                    clock[0]=5.1;on_idle(clock[0])
                    self.fail('Silent reader must be closed before configuring again')
                for n in range(700):
                    clock[0]+=.004
                    phase=np.arange(8)*.2
                    adc=np.rint(10_000+500*np.sin(2*np.pi*10*n/250+phase)).astype(int)
                    packet=bytearray((0xA0,n%256))
                    for value in adc:packet.extend((int(value)&0xffffff).to_bytes(3,'big'))
                    packet.extend(bytes(6));packet.append(0xC0)
                    yield bytes(packet),0,clock[0]
                if opens[0]==2:
                    clock[0]+=.6;on_idle(clock[0])
                    self.assertFalse(results[-1]['valid'])
                    self.assertEqual(results[-1]['reason'],'STREAM_IDLE')
                    clock[0]+=5.1;on_idle(clock[0])
            patches=dict(
                time=SimpleNamespace(monotonic=lambda:clock[0],time=lambda:clock[0],sleep=lambda _:None),
                configure_serial=Mock(),configure_eeg_channels=configuration,write_command=commands,
                packets=frames,TrialRecorder=lambda *_:recorder,
                TelemetryWriter=lambda:Mock(),GuardianLoopPynq=Mock(side_effect=AssertionError('No PL')),
                SeedShadow=Mock(side_effect=OSError('isolated test')),
                SSVEPReaderRuntime=Mock(side_effect=OSError('isolated test')),
                LIVE_PATH=root/'seed',SSVEP_PATH=root/'ssvep',
                publish_result=lambda result,*a,**k:results.append(result.copy()))
            argv=['wait-test','--port','/dev/null','--wait-for-data',
                  '--status-file',str(root/'status'),'--telemetry-file',str(root/'telemetry'),
                  '--covariance-model',str(root/'missing-cov'),'--emotion-model',str(root/'missing-emotion'),
                  '--fatigue-model',str(root/'missing-fatigue')]
            log=io.StringIO()
            with patch.multiple(live,**patches),patch.object(live.termios,'tcflush'),\
                    patch.object(live.signal,'signal'),\
                    patch('sys.argv',argv),contextlib.redirect_stdout(log):
                live.main()
            self.assertIn('CYTON_NO_PACKETS_RECONNECT',[r.get('reason') for r in results])
            self.assertEqual(log.getvalue().count('PRIMARY_STREAM_RESET:'),2)
            self.assertEqual(log.getvalue().count('CYTON_RECONFIGURING:'),2)
            self.assertEqual(configuration.call_count,3)
            self.assertFalse(any(r.get('valid') for r in results))
            self.assertTrue(all(r.get('emotion',{}).get('valid') is not True for r in results))
            self.assertEqual(commands.call_count,7)


if __name__=='__main__':unittest.main()

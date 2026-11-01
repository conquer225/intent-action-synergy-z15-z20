import io,unittest,wave
import numpy as np


class SoundInputTests(unittest.TestCase):
 def wav(self,samples,rate=16000):
  stream=io.BytesIO()
  with wave.open(stream,'wb') as output:
   output.setnchannels(1);output.setsampwidth(2);output.setframerate(rate)
   output.writeframes(np.asarray(samples,dtype='<i2').tobytes())
  return stream.getvalue()
 def test_wav_produces_one_real_model_window_and_rejects_silence(self):
  from z20_compute.sound_input import decode_sound_wav,prepare_sound_input
  raw=(np.sin(np.arange(16000)*2*np.pi*1000/16000)*12000).astype(np.int16)
  samples=decode_sound_wav(self.wav(raw))
  np.testing.assert_array_equal(samples,raw/32768.)
  result=prepare_sound_input(samples,source='live:pc_microphone')
  self.assertEqual(len(result['vector']),40);self.assertTrue(result['valid'])
  invalid=prepare_sound_input(decode_sound_wav(self.wav(np.zeros(16000))),source='recorded:pc_wav')
  self.assertFalse(invalid['valid']);self.assertIsNone(invalid['vector'])

 def test_uploaded_sound_reaches_the_same_classifier_and_old_origins_are_rejected(self):
  import json,time,urllib.request,urllib.error
  from pathlib import Path
  from z20_compute.visual_offline import OfflineBoard
  from z20_compute.visual_host import VisualHost,start_http
  root=Path(__file__).resolve().parents[1]
  with OfflineBoard(root) as board:
   host=VisualHost('127.0.0.1',board.token,control_port=board.server.control_port,frame_port=board.server.frame_port).start()
   server=start_http(host,0);url='http://127.0.0.1:%d'%server.server_port
   try:
    deadline=time.monotonic()+2
    while not host.snapshot().get('renderer_online') and time.monotonic()<deadline:time.sleep(.01)
    for name in ('right','right','enter'):host.command(name)
    data=self.wav((np.sin(np.arange(16000)*2*np.pi*1000/16000)*12000).astype(np.int16))
    def request(origin):return urllib.request.Request(url+'/api/sound',data=data,headers={'Content-Type':'audio/wav','X-Sound-Source':'microphone','Origin':origin})
    with self.assertRaises(urllib.error.HTTPError) as rejection:urllib.request.urlopen(request('http://another-site'),timeout=2)
    rejection.exception.close()
    with urllib.request.urlopen(request(url),timeout=2) as response:reply=json.load(response)
    self.assertTrue(reply['accepted'])
    deadline=time.monotonic()+2;trace={}
    while time.monotonic()<deadline:
     trace=host.snapshot().get('data',{}).get('npu',{})
     if trace.get('window_id')==reply['window_id'] and trace.get('event')=='completed':break
     time.sleep(.01)
    self.assertEqual(trace['source'],'live:pc_microphone')
    self.assertEqual(trace['backend'],'PS_integer_reference')
    self.assertEqual(len(trace['features']),40)
   finally:host.close();server.shutdown();server.server_close()

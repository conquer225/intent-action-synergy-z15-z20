import unittest
import numpy as np
from vision_demo.signal_charts import spectrogram, covariance_maps, wave_scale, pcm_wave_scale

class SignalChartTests(unittest.TestCase):
 def test_spectrum_columns_keep_real_band_peaks_and_empty_frequency_gaps(self):
  from vision_demo.signal_charts import spectrum_columns
  frequency=np.array([20.,50.,100.,150.,199.,200.,500.,2000.,19999.,20000.,24000.])
  db=np.array([-70.,-60.,-20.,-10.,-30.,-50.,-40.,-65.,-70.,-60.,0.])
  original=db.copy();chart=spectrum_columns(frequency,db,count=3)
  np.testing.assert_allclose(chart['edges_hz'],[20.,200.,2000.,20000.])
  np.testing.assert_allclose(chart['peak_dbfs'],[-10.,-40.,-60.])
  np.testing.assert_array_equal(db,original)
  gap=spectrum_columns([500.,1000.],[-40.,-60.],count=3)
  self.assertTrue(np.isnan(gap['peak_dbfs'][0]));self.assertTrue(np.isnan(gap['peak_dbfs'][2]))
  self.assertEqual(gap['peak_dbfs'][1],-40.)
 def test_exact_decade_boundaries_belong_to_the_next_band(self):
  from vision_demo.signal_charts import spectrum_columns
  chart=spectrum_columns([20.,200.,2000.,20000.],[-70.,-60.,-50.,-40.],count=3)
  np.testing.assert_allclose(chart['peak_dbfs'],[-70.,-60.,-40.])
 def test_spectrogram_places_ten_hz_energy_at_measured_frequency(self):
  t=np.arange(200)/50.;samples=np.tile(np.sin(2*np.pi*10*t)[:,None],(1,8))
  chart=spectrogram(samples,50)
  peak=chart['frequency_hz'][np.argmax(np.mean(chart['power_db'],axis=1))]
  self.assertAlmostEqual(peak,10,delta=.8)
  self.assertLessEqual(max(chart['frequency_hz']),25)
  self.assertAlmostEqual(chart['time_seconds'][-1],3.36,places=2)
  self.assertIsNone(spectrogram([],50))
 def test_covariance_maps_undo_weighted_upper_triangle_without_inference(self):
  values=np.zeros(105);values[0]=3;values[1]=2*np.sqrt(2);values[6]=4;values[21]=7
  maps=covariance_maps(values)
  self.assertEqual(maps.shape,(5,6,6))
  np.testing.assert_allclose(maps[0,:2,:2],[[3,2],[2,4]])
  self.assertEqual(maps[1,0,0],7)
  self.assertIsNone(covariance_maps([1]*104))
 def test_wave_scale_is_shared_physical_uv_and_does_not_normalize_each_channel(self):
  values=np.tile(np.array([1,2,3,4,5,6,7,8]),(200,1))
  self.assertEqual(wave_scale(values),10)
  self.assertEqual(wave_scale(np.zeros((200,8))),5)
  np.testing.assert_array_equal(values[0],[1,2,3,4,5,6,7,8])


 def test_stereo_wave_scale_preserves_relative_channels_and_full_scale_units(self):
  self.assertEqual(pcm_wave_scale([[.011,-.004],[0,0]]),.02)
  self.assertEqual(pcm_wave_scale([[.25,-.1]]),.5)
  self.assertEqual(pcm_wave_scale([[1,-.5]]),1.)
  self.assertEqual(pcm_wave_scale([[0,0]]),.01)

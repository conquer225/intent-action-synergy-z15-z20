import unittest
from z20_compute.headless_keys import Navigation


class DisplayContractTests(unittest.TestCase):
    def test_expired_person_dog_geometry_and_uncalibrated_depth_never_reappear(self):
        from z20_compute.headless_display import describe_view
        snapshot=dict(page='person_dog',detail=0,results={},environment={
            'person_dog':dict(valid=False,state='expired',payload=dict(interaction='petting',
                geometry=dict(person_depth_m=2.,dog_depth_m=3.,distance_m=1.))),
            'depth':dict(valid=False,state='uncalibrated',payload=dict(distance_m=9.))})
        view=describe_view(snapshot)
        self.assertEqual(view['primary'],'未识别')
        self.assertNotIn('1.00',' '.join(view['lines']))
        snapshot['page']='depth';view=describe_view(snapshot)
        self.assertEqual(view['primary'],'-- m')
        self.assertIn('未标定',' '.join(view['lines']))

    def test_all_nine_pages_have_distinct_titles_and_contextual_key2_help(self):
        from z20_compute.headless_display import describe_view
        views=[describe_view(dict(page=p,detail=0,results={},environment={})) for p in Navigation.PAGES]
        self.assertEqual(len(set(v['title'] for v in views)),9)
        self.assertTrue(all('KEY2' in v['footer'] for v in views))
        self.assertEqual(describe_view(dict(page='adda',detail=0,results={},environment={}))['primary'],'接口准备')


if __name__=='__main__':unittest.main()

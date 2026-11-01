import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import app
import place_data

class PlaceDataTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.old=app.DB
        app.DB=str(Path(self.tmp.name)/'test.db');app.initialize();app.enable_xintiandi_demo()
        self.place=next(p for p in app.state()['places'] if p['name']=='复兴公园')
    def tearDown(self):
        app.DB=self.old;self.tmp.cleanup()
    def response(self,pois):
        return io.BytesIO(json.dumps({'status':'1','pois':pois}).encode())
    def poi(self):
        return {'id':'test-poi','name':'复兴公园','location':'121.47,31.215','address':'雁荡路105号','business':{'rating':'4.7'}}
    def test_missing_key_never_calls_network(self):
        with patch.dict(os.environ,{},clear=True),patch('place_data.urlopen') as request:
            r=app.place_context(self.place['id']);request.assert_not_called()
            self.assertEqual(r['facts']['status'],'not_configured');self.assertIsNone(r['live_crowd'])
            self.assertEqual(r['public_experiences'][0]['author'],'Travelwithfei')
    def test_unique_match_does_not_overwrite_wgs84(self):
        before=(self.place['lat'],self.place['lon'])
        with patch.dict(os.environ,{'AMAP_WEB_SERVICE_KEY':'test-secret'}),patch('place_data.urlopen',return_value=self.response([self.poi()])):
            r=app.place_context(self.place['id'])
        self.assertEqual(r['facts']['rating'],'4.7');self.assertEqual(r['facts']['coordinate_system'],'GCJ-02')
        after=next(p for p in app.state()['places'] if p['id']==self.place['id'])
        self.assertEqual(before,(after['lat'],after['lon']));self.assertNotIn('test-secret',json.dumps(r))
    def test_duplicate_and_distant_matches_rejected(self):
        for pois in ([self.poi(),self.poi()],[dict(self.poi(),location='116.4,39.9')]):
            with patch.dict(os.environ,{'AMAP_WEB_SERVICE_KEY':'key'}),patch('place_data.urlopen',return_value=self.response(pois)):
                self.assertEqual(place_data.fetch_amap_facts(self.place)['status'],'ambiguous')
    def test_network_error_never_exposes_key(self):
        with patch.dict(os.environ,{'AMAP_WEB_SERVICE_KEY':'secret'}),patch('place_data.urlopen',side_effect=ValueError('https://example?key=secret')):
            self.assertNotIn('secret',json.dumps(place_data.fetch_amap_facts(self.place)))
    def test_experience_validation_and_separation(self):
        payload=dict(place_id=self.place['id'],summary='我读到的历史体验',author='测试作者',platform='用户分享',url='https://example.org/post',published='2025-06-19')
        app.action('/api/experiences',payload)
        with patch.dict(os.environ,{},clear=True):r=app.place_context(self.place['id'])
        self.assertEqual(r['user_experiences'][0]['source_type'],'user_supplied')
        self.assertEqual(app.state()['evidence'],[])
        self.assertEqual(next(p for p in app.state()['places'] if p['id']==self.place['id'])['wanted'],0)
        for url in ('javascript:alert(1)','file:///tmp/private','http://example.org'):
            with self.assertRaises(ValueError):app.action('/api/experiences',dict(payload,url=url))
    def test_delete_clears_supplied_experiences(self):
        app.action('/api/experiences',dict(place_id=self.place['id'],summary='体验摘要',author='作者',platform='来源',url='https://example.org',published='2025-01-01'))
        app.action('/api/delete-data',{})
        with app.db() as c:self.assertEqual(c.execute('SELECT count(*) FROM experiences').fetchone()[0],0)
    def test_historical_sample_is_attributed_not_crowd(self):
        sample=place_data.public_experiences(self.place)[0]
        self.assertEqual(sample['sample_count'],1);self.assertEqual(sample['published'],'2025-06-19')
        self.assertIn('不能证明今天',sample['limitation'])
        self.assertEqual(place_data.public_experiences(dict(self.place,origin='user')),[])

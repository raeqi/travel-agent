import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import app

class AgentTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.old=app.DB
        app.DB=str(Path(self.tmp.name)/'test.db')
        app.initialize()
        app.action('/api/places',dict(name='书店',category='书店',lat=31.23,lon=121.47,source='用户官网核实',note='喜欢建筑选书'))
        app.action('/api/settings',dict(proactive=True,minutes=60))
    def tearDown(self):
        app.DB=self.old
        self.tmp.cleanup()
    def locate(self,accuracy=10):
        return app.action('/api/location',dict(lat=31.23,lon=121.47,accuracy=accuracy))
    def test_proactive_and_cooldown(self):
        self.assertEqual(len(self.locate()['recommendations']),1)
        self.assertEqual(app.evaluate()['recommendations'],[])
        self.assertEqual(len(app.state()['messages']),1)
    def test_stale_and_inaccurate_position(self):
        self.assertEqual(self.locate(500)['recommendations'],[])
        with app.db() as c:
            c.execute('UPDATE locations SET observed=?,accuracy=10',(app.now()-1801,))
        self.assertIn('位置', app.evaluate()['decision'])
    def test_expired_place_not_recommended(self):
        with app.db() as c:c.execute('UPDATE places SET expires=0')
        self.assertEqual(self.locate()['recommendations'],[])
    def test_later_retains_interest_visited_removes(self):
        self.locate()
        app.action('/api/feedback',dict(place_id=1,kind='later',text='赶时间'))
        self.assertEqual(app.state()['places'][0]['wanted'],1)
        app.action('/api/feedback',dict(place_id=1,kind='visited',text='陪朋友去，不代表喜欢'))
        self.assertEqual(app.evaluate('ask',False)['recommendations'],[])
        self.assertEqual(len(app.state()['evidence']),3)
    def test_disabled(self):
        app.action('/api/settings',dict(proactive=False,minutes=60))
        self.assertEqual(self.locate()['recommendations'],[])
        self.assertEqual(len(app.evaluate('ask',False)['recommendations']),1)
    def test_validation(self):
        for lat in ('nan',91,'inf'):
            with self.assertRaises(ValueError):app.action('/api/location',dict(lat=lat,lon=0,accuracy=1))
    def test_delete(self):
        self.locate()
        app.action('/api/delete-data',{})
        s=app.state()
        self.assertEqual(s['places'],[])
        self.assertIsNone(s['location'])
        self.assertFalse(s['settings']['proactive'])
    def test_concurrent_checks_single_delivery(self):
        from concurrent.futures import ThreadPoolExecutor
        with app.db() as c:c.execute('INSERT INTO locations(lat,lon,accuracy,observed) VALUES(31.23,121.47,10,?)',(app.now(),))
        with ThreadPoolExecutor(max_workers=4) as pool:list(pool.map(lambda _:app.evaluate(),range(4)))
        self.assertEqual(len(app.state()['messages']),1)

if __name__=='__main__':unittest.main()

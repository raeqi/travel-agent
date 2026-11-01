import tempfile
import unittest
from pathlib import Path
import app
from nearby import PLACES

class DiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.old=app.DB
        app.DB=str(Path(self.tmp.name)/'test.db');app.initialize()
    def tearDown(self):
        app.DB=self.old;self.tmp.cleanup()
    def test_demo_proactively_sends_without_favorite(self):
        r=app.enable_xintiandi_demo();s=app.state()
        self.assertEqual(len(r['recommendations']),1)
        self.assertTrue(s['location']['simulated'])
        self.assertTrue(s['settings']['proactive'])
        self.assertEqual(len(s['places']),len(PLACES))
        self.assertFalse(any(p['wanted'] for p in s['places']))
        self.assertEqual(s['evidence'],[])
        self.assertNotIn('你想去的',s['messages'][0]['text'])
    def test_repeated_demo_does_not_duplicate_or_spam(self):
        app.enable_xintiandi_demo();app.enable_xintiandi_demo()
        self.assertEqual(len(app.state()['places']),len(PLACES))
        self.assertEqual(len(app.state()['messages']),1)
    def test_dislike_removes_nearby_candidate(self):
        first=app.enable_xintiandi_demo()['recommendations'][0]['place']['id']
        app.action('/api/feedback',dict(place_id=first,kind='dislike',text='我不想去'))
        r=app.evaluate('user',False)
        self.assertNotIn(first,[x['place']['id'] for x in r['recommendations']])
    def test_discovery_does_not_follow_user_to_other_city(self):
        app.enable_xintiandi_demo()
        app.action('/api/location',dict(lat=39.9,lon=116.4,accuracy=10))
        self.assertEqual(app.evaluate('user',False)['recommendations'],[])
    def test_open_page_obeys_cooldown(self):
        app.enable_xintiandi_demo();app.action('/api/pulse',{})
        self.assertEqual(len(app.state()['messages']),1)

    def test_food_catalog_is_discovery_not_user_interest(self):
        app.enable_xintiandi_demo()
        places=app.state()['places']
        self.assertEqual(len([p for p in places if '咖啡' in p['category']]),2)
        self.assertEqual(len([p for p in places if '餐厅' in p['category']]),3)
        self.assertFalse(any(p['wanted'] for p in places))
        self.assertTrue(all(p['source'].startswith('https://') for p in places))
    def test_catalog_upgrade_keeps_location_and_consent(self):
        app.enable_xintiandi_demo()
        app.action('/api/settings',dict(proactive=False,minutes=30))
        old=app.state()['location']
        with app.db() as c:c.execute("DELETE FROM places WHERE category LIKE '咖啡%' OR category LIKE '餐厅%'")
        app.initialize()
        self.assertEqual(app.state()['location'],old)
        self.assertFalse(app.state()['settings']['proactive'])
        self.assertEqual(len(app.state()['places']),len(PLACES))

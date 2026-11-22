"""Phase-one behaviour: shared candidates, feedback expiry and legacy migration."""
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import app


class ExplorationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = app.DB
        app.DB = str(Path(self.tmp.name) / 'phase1.db')
        self.clock = patch('app.now', return_value=1_800_000_000)
        self.now = self.clock.start()
        app.initialize()

    def tearDown(self):
        self.clock.stop()
        app.DB = self.old
        self.tmp.cleanup()

    def place(self, name='测试咖啡', lat=31.223, lon=121.4752):
        app.action('/api/places', dict(name=name, category='咖啡', lat=lat, lon=lon, source='合成测试点', note='只供测试'))
        return app.state()['places'][0]['id']

    def locate(self, minutes=60):
        app.action('/api/settings', dict(proactive=True, minutes=minutes))
        return app.action('/api/location', dict(lat=31.2197, lon=121.4752, accuracy=20))

    def ids(self):
        return [r['place']['id'] for r in app.state()['exploration']['recommendations']]

    def test_six_minute_walk_requires_32_minutes_on_every_path(self):
        pid = self.place()
        self.locate(30)
        self.assertEqual(self.ids(), [])
        self.assertEqual(app.evaluate('conversation', False)['recommendations'], [])
        self.assertEqual(app.evaluate('timer', True)['recommendations'], [])
        self.assertEqual(app.state()['messages'], [])
        app.action('/api/settings', dict(proactive=True, minutes=35))
        snapshot = app.state()['exploration']
        item = snapshot['recommendations'][0]
        self.assertEqual(item['place']['id'], pid)
        self.assertEqual(item['walking_minutes_estimate'], 6)
        self.assertEqual(item['round_trip_minutes_estimate'], 12)
        self.assertEqual(item['stop_minutes_assumption'], 20)
        self.assertEqual(item['total_minutes_estimate'], 32)
        self.assertEqual(app.evaluate('conversation', False)['recommendations'], snapshot['recommendations'])
        self.assertEqual(app.evaluate('timer', True)['recommendations'], snapshot['recommendations'])
        self.assertIn('非导航路线', item['text'])

    def test_snooze_persists_and_expires_without_changing_interest(self):
        pid = self.place(); self.locate()
        until = app.now() + 86400
        app.action('/api/feedback', dict(place_id=pid, kind='later', text='今天赶时间', snoozed_until=until))
        self.assertEqual(self.ids(), [])
        self.assertEqual(app.evaluate('conversation', False)['recommendations'], [])
        app.initialize()  # restart must not reset either state or evidence
        self.assertEqual(self.ids(), [])
        p = app.state()['places'][0]
        self.assertEqual(p['wanted'], 1)
        self.assertEqual(p['interest_state'], 'active')
        self.assertEqual(p['snoozed_until'], until)
        self.assertEqual(app.state()['evidence'][0]['snoozed_until'], until)
        self.now.return_value = until - 1
        self.locate(); self.assertEqual(self.ids(), [])
        self.now.return_value = until
        self.locate()
        self.assertEqual(self.ids(), [pid])
        self.assertEqual(len(app.state()['messages']), 2)  # old snoozed delivery does not impose 7-day block

    def test_snooze_requires_valid_explicit_future_expiry(self):
        pid = self.place()
        for value in (None, '', app.now()-1, True, 'nan', app.now()+400*86400):
            with self.assertRaises(ValueError):
                app.action('/api/feedback', dict(place_id=pid, kind='later', text='稍后', snoozed_until=value))
        self.assertEqual(len(app.state()['evidence']), 1)

    def test_snooze_undo_keeps_history_and_cooldown(self):
        pid = self.place(); self.locate()
        app.action('/api/feedback', dict(place_id=pid, kind='later', text='过会儿', snoozed_until=app.now()+3600))
        app.action('/api/feedback', dict(place_id=pid, kind='undo-later', text='现在有空'))
        self.assertEqual(self.ids(), [pid])
        self.assertIn('冷却', app.evaluate()['decision'])
        self.assertEqual(app.state()['evidence'][1]['text'], '过会儿')

    def test_dislike_and_undo_work_for_nearby_and_personal_places(self):
        app.enable_xintiandi_demo()
        personal = self.place('个人地点')
        nearby = next(p['id'] for p in app.state()['places'] if p['origin']=='nearby')
        for pid in (personal, nearby):
            before = next(p for p in app.state()['places'] if p['id']==pid)
            app.action('/api/feedback', dict(place_id=pid, kind='dislike', text='明确不喜欢这个地点'))
            app.initialize()
            self.assertNotIn(pid, self.ids())
            app.action('/api/feedback', dict(place_id=pid, kind='undo-dislike', text='恢复资格'))
            self.assertIn(pid, self.ids())
            restored = next(p for p in app.state()['places'] if p['id']==pid)
            self.assertEqual(restored['wanted'], before['wanted'])
            self.assertEqual(restored['interest_state'], 'active')
        self.assertEqual(len([e for e in app.state()['evidence'] if e['kind']=='dislike']), 2)

    def test_location_staleness_invalidates_inbox_actions_and_start(self):
        pid = self.place(); self.locate()
        self.assertEqual(len(app.state()['messages']), 1)
        self.now.return_value += 1801
        self.assertEqual(self.ids(), [])
        self.assertEqual(app.evaluate()['recommendations'], [])
        with self.assertRaises(ValueError): app.action('/api/start-exploration', dict(place_id=pid))
        self.assertEqual(len(app.state()['messages']), 1)  # keep history, hide action using shared eligibility

    def test_cooldown_only_controls_delivery(self):
        pid = self.place(); self.locate()
        self.assertIn('冷却', app.evaluate()['decision'])
        self.assertEqual(self.ids(), [pid])
        self.assertEqual([x['place']['id'] for x in app.evaluate('conversation', False)['recommendations']], [pid])

    def test_unlocated_wish_is_saved_and_never_gets_fake_coordinates(self):
        pid = self.place(lat='', lon='')
        self.locate()
        p = app.state()['places'][0]
        self.assertIsNone(p['lat']); self.assertIsNone(p['lon'])
        self.assertEqual(self.ids(), [])
        with self.assertRaises(ValueError):
            app.action('/api/places', dict(name='半个坐标',category='咖啡',lat=31,source='合成'))
        app.action('/api/place-location', dict(place_id=pid,lat=31.2197,lon=121.4752,source='确认合成点'))
        self.assertEqual(self.ids(), [pid])

    def test_old_later_without_expiry_is_preserved_not_guessed(self):
        pid = self.place()
        with app.db() as c:
            c.execute("INSERT INTO evidence(place_id,kind,text,created) VALUES(?,'later','旧稍后原话',?)", (pid,app.now()-3600))
        app.initialize()
        self.assertIsNone(app.state()['places'][0]['snoozed_until'])
        self.assertIsNone(app.state()['evidence'][0]['snoozed_until'])
        self.assertEqual(app.state()['evidence'][0]['text'], '旧稍后原话')

    def test_old_schema_migrates_ids_references_dislike_and_nullable_location(self):
        Path(app.DB).unlink()
        c = sqlite3.connect(app.DB)
        c.executescript('''
        CREATE TABLE places(id INTEGER PRIMARY KEY,name TEXT NOT NULL,lat REAL NOT NULL,lon REAL NOT NULL,category TEXT NOT NULL,source TEXT NOT NULL,verified REAL NOT NULL,expires REAL NOT NULL,wanted INTEGER DEFAULT 1,visited INTEGER DEFAULT 0,note TEXT DEFAULT '');
        CREATE TABLE evidence(id INTEGER PRIMARY KEY,place_id INTEGER,kind TEXT NOT NULL,text TEXT NOT NULL,created REAL NOT NULL);
        INSERT INTO places VALUES(42,'旧收藏',31.2197,121.4752,'咖啡','旧来源',1,1900000000,0,0,'旧说明');
        INSERT INTO evidence VALUES(1,42,'dislike','旧拒绝原话',2);
        '''); c.commit(); c.close()
        app.initialize(); self.locate()
        p = app.state()['places'][0]
        self.assertEqual(p['id'],42); self.assertEqual(p['interest_state'],'disliked')
        self.assertEqual(self.ids(), [])
        app.action('/api/feedback', dict(place_id=42,kind='undo-dislike',text='撤销'))
        app.initialize()
        self.assertEqual(self.ids(), [42])  # migration must not replay old dislike
        pid = self.place('未定位旧库新增',None,None)
        self.assertIsNone(app.state()['places'][0]['lat'])
        self.assertNotIn(pid, self.ids())

if __name__ == '__main__': unittest.main()

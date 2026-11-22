"""Wander: single-user, local-first proactive geographic exploration agent."""
import argparse
import json
import math
import os
import sqlite3
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).parent
DB = os.environ.get('WANDER_DB', str(ROOT / 'data' / 'wander.db'))

def now():
    return time.time()

@contextmanager
def db():
    Path(DB).parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB, timeout=15)
    con.row_factory = sqlite3.Row
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()

def initialize():
    with db() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS places(id INTEGER PRIMARY KEY, name TEXT NOT NULL, lat REAL, lon REAL, category TEXT NOT NULL, source TEXT NOT NULL, verified REAL NOT NULL, expires REAL NOT NULL, wanted INTEGER DEFAULT 1, visited INTEGER DEFAULT 0, note TEXT DEFAULT '');
        CREATE TABLE IF NOT EXISTS experiences(id INTEGER PRIMARY KEY, place_id INTEGER NOT NULL, summary TEXT NOT NULL, author TEXT NOT NULL, platform TEXT NOT NULL, url TEXT NOT NULL, published TEXT NOT NULL, source_type TEXT NOT NULL, limitation TEXT NOT NULL, created REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS evidence(id INTEGER PRIMARY KEY, place_id INTEGER, kind TEXT NOT NULL, text TEXT NOT NULL, created REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS locations(id INTEGER PRIMARY KEY, lat REAL NOT NULL, lon REAL NOT NULL, accuracy REAL NOT NULL, observed REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS messages(id INTEGER PRIMARY KEY, place_id INTEGER, text TEXT NOT NULL, created REAL NOT NULL, status TEXT DEFAULT 'new');
        CREATE TABLE IF NOT EXISTS runs(id INTEGER PRIMARY KEY, trigger TEXT NOT NULL, decision TEXT NOT NULL, created REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS migrations(name TEXT PRIMARY KEY);
        CREATE TABLE IF NOT EXISTS settings(id INTEGER PRIMARY KEY CHECK(id=1), proactive INTEGER DEFAULT 0, minutes INTEGER DEFAULT 60, cooldown INTEGER DEFAULT 21600);
        INSERT OR IGNORE INTO settings(id) VALUES(1);
        ''')
        # Keep all data/schema upgrades atomic; a failed migration must leave
        # the previous places table and its references intact.
        c.execute('BEGIN IMMEDIATE')
        for table, column, definition in (
            ('places', 'origin', "TEXT NOT NULL DEFAULT 'user'"),
            ('locations', 'simulated', 'INTEGER NOT NULL DEFAULT 0'),
            ('locations', 'label', "TEXT NOT NULL DEFAULT ''"),
            ('evidence', 'snoozed_until', 'REAL'),
        ):
            if column not in [r['name'] for r in c.execute('PRAGMA table_info('+table+')')]:
                c.execute('ALTER TABLE '+table+' ADD COLUMN '+column+' '+definition)
        # Old installs required coordinates. Rebuild only that known schema so an
        # unlocated wish can be stored as NULL, never as a fabricated point.
        if any(r['name'] == 'lat' and r['notnull'] for r in c.execute('PRAGMA table_info(places)')):
            c.execute('ALTER TABLE places RENAME TO places_with_required_coordinates')
            c.execute("CREATE TABLE places(id INTEGER PRIMARY KEY, name TEXT NOT NULL, lat REAL, lon REAL, category TEXT NOT NULL, source TEXT NOT NULL, verified REAL NOT NULL, expires REAL NOT NULL, wanted INTEGER DEFAULT 1, visited INTEGER DEFAULT 0, note TEXT DEFAULT '', origin TEXT NOT NULL DEFAULT 'user')")
            columns = 'id,name,lat,lon,category,source,verified,expires,wanted,visited,note,origin'
            c.execute('INSERT INTO places('+columns+') SELECT '+columns+' FROM places_with_required_coordinates')
            c.execute('DROP TABLE places_with_required_coordinates')
        for column, definition in (('snoozed_until', 'REAL'), ('interest_state', "TEXT NOT NULL DEFAULT 'active'")):
            if column not in [r['name'] for r in c.execute('PRAGMA table_info(places)')]:
                c.execute('ALTER TABLE places ADD COLUMN '+column+' '+definition)
        if not c.execute("SELECT 1 FROM migrations WHERE name='feedback-state-v1'").fetchone():
            # Original dislike cleared wanted. Preserve that explicit exclusion,
            # and retain the prior personal wish for a later undo. Legacy 'later'
            # has no known expiry and is deliberately not assigned a guessed one.
            c.execute("UPDATE places SET interest_state='disliked' WHERE EXISTS (SELECT 1 FROM evidence WHERE evidence.place_id=places.id AND evidence.kind='dislike')")
            c.execute("UPDATE places SET wanted=1 WHERE origin='user' AND visited=0 AND interest_state='disliked'")
            c.execute("INSERT INTO migrations VALUES('feedback-state-v1')")
        # Upgrade the existing demo catalog without resetting location or consent.
        if c.execute("SELECT 1 FROM places WHERE origin='nearby' LIMIT 1").fetchone():
            insert_catalog(c)

def insert_catalog(c):
    from nearby import PLACES
    t=now()
    for p in PLACES:
        if not c.execute("SELECT 1 FROM places WHERE name=? AND origin='nearby'", (p['name'],)).fetchone():
            c.execute("INSERT INTO places(name,lat,lon,category,source,verified,expires,wanted,note,origin) VALUES(?,?,?,?,?,?,?,0,?,'nearby')",
                      (p['name'],p['lat'],p['lon'],p['category'],p['source'],t,t+7*86400,p['note']))

def enable_xintiandi_demo():
    with db() as c:
        c.execute("INSERT INTO locations(lat,lon,accuracy,observed,simulated,label) VALUES(31.2197,121.4752,100,?,1,'上海 · 新天地附近')", (now(),))
        c.execute('UPDATE settings SET proactive=1 WHERE id=1')
        insert_catalog(c)
    return evaluate('simulated-location', True)

def distance(a, b, x, y):
    r = math.pi / 180
    h = math.sin((x-a)*r/2)**2 + math.cos(a*r)*math.cos(x*r)*math.sin((y-b)*r/2)**2
    return 6371000 * 2 * math.asin(min(1, math.sqrt(h)))

def finite_number(value, low, high, field):
    if isinstance(value, bool):
        raise ValueError(field + ' 必须是数字')
    try:
        v = float(value)
    except (ValueError, TypeError):
        raise ValueError(field + ' 必须是数字')
    if not math.isfinite(v) or not low <= v <= high:
        raise ValueError(field + ' 超出范围')
    return v

def text_field(data, key, limit=1000):
    s = str(data.get(key, '')).strip()
    if not s or len(s) > limit:
        raise ValueError(key + ' 为空或过长')
    return s

WALK_METERS_PER_MINUTE = 65
STOP_MINUTES = 20

def exploration_snapshot(c, t):
    """The single eligibility decision used by map, conversation and delivery.

    This is a time budget over straight-line distance, not routing. Snooze is a
    temporary exclusion; dislike is an explicit preference until reversed.
    Notification cooldown/dedup are delivery gates and do not hide valid places.
    """
    settings = dict(c.execute('SELECT * FROM settings WHERE id=1').fetchone())
    row = c.execute('SELECT * FROM locations ORDER BY observed DESC, id DESC LIMIT 1').fetchone()
    loc = dict(row) if row else None
    reason = None
    if not loc or t-loc['observed'] > 1800:
        reason = '位置缺失或已超过 30 分钟，等待新位置'
    elif loc['accuracy'] > 200:
        reason = '定位精度不足，保持安静'
    recommendations = []
    if not reason:
        for row in c.execute("SELECT * FROM places WHERE visited=0 AND (wanted=1 OR origin='nearby') AND interest_state='active'"):
            p = dict(row)
            if p['expires'] < t or p['lat'] is None or p['lon'] is None:
                continue
            if p['snoozed_until'] is not None and p['snoozed_until'] > t:
                continue
            meters = distance(loc['lat'], loc['lon'], p['lat'], p['lon'])
            if p['origin'] == 'nearby' and meters > 2000:
                continue
            walking = math.ceil(meters / WALK_METERS_PER_MINUTE)
            total = walking*2 + STOP_MINUTES
            if total > settings['minutes']:
                continue
            prefix = '你想去的' if p['wanted'] else '我发现'
            msg = (f"{prefix}「{p['name']}」在附近，单程步行粗估 {walking} 分钟；"
                   f"往返 {walking*2} 分钟 + 停留 {STOP_MINUTES} 分钟，合计粗估 {total} 分钟。"
                   f"按直线距离、每分钟 {WALK_METERS_PER_MINUTE} 米估算，非导航路线；不计等候。"
                   f"{p['note']} 信息来源：{p['source']}。营业状态尚未核实，出发前请确认。")
            from place_data import public_experiences
            observations = public_experiences(p)
            if observations:
                item = observations[0]
                msg += f" 体验线索：{item['summary']}（{item['platform']}，{item['published']}，1 篇样本，不代表当前客流）。"
            recommendations.append({'place': decorate_place(p), 'walking_minutes_estimate': walking,
                                    'round_trip_minutes_estimate': walking*2,
                                    'stop_minutes_assumption': STOP_MINUTES,
                                    'total_minutes_estimate': total,
                                    'distance_meters_estimate': round(meters), 'text': msg})
        recommendations.sort(key=lambda x: (x['walking_minutes_estimate'], x['place']['id']))
        if not recommendations:
            reason = '没有信息有效且在可用时间内的待探索地点'
    return {'evaluated_at': t, 'decision': reason or f'返回 {len(recommendations)} 个候选',
            'recommendations': recommendations, 'minutes_available': settings['minutes'],
            'assumptions': {'walking_meters_per_minute': WALK_METERS_PER_MINUTE,
                            'stop_minutes': STOP_MINUTES, 'distance': 'straight_line',
                            'includes_return': True, 'includes_waiting': False}}

def evaluate(trigger='timer', proactive=True):
    """Atomic eligibility + delivery: concurrent checks cannot double-send."""
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        t = now()
        snapshot = exploration_snapshot(c, t)
        settings = c.execute('SELECT * FROM settings WHERE id=1').fetchone()
        reason = None
        if proactive and not settings['proactive']:
            reason = '主动建议未开启'
        elif not snapshot['recommendations']:
            reason = snapshot['decision']
        elif proactive and c.execute('SELECT 1 FROM messages WHERE created>? LIMIT 1', (t-settings['cooldown'],)).fetchone():
            reason = '处于通知冷却期'
        candidates = snapshot['recommendations']
        if proactive:
            candidates = [x for x in candidates if not c.execute(
                "SELECT 1 FROM messages WHERE place_id=? AND created>? AND status NOT IN ('later','dislike') LIMIT 1",
                (x['place']['id'], t-7*86400)).fetchone()]
        if not reason and not candidates:
            reason = snapshot['decision'] if not snapshot['recommendations'] else '近期已推荐过这些地点，保持安静'
        result = [] if reason else candidates[:1 if proactive else len(candidates)]
        if proactive:
            for item in result:
                c.execute('INSERT INTO messages(place_id,text,created) VALUES(?,?,?)', (item['place']['id'], item['text'], t))
        decision = reason or ('已发送主动建议' if proactive else f'返回 {len(result)} 个候选')
        c.execute('INSERT INTO runs(trigger,decision,created) VALUES(?,?,?)', (trigger, decision, t))
        return dict(snapshot, decision=decision, recommendations=result)

def decorate_place(p):
    from place_data import public_experiences
    samples=public_experiences(p)
    return dict(p, experience_preview=samples[0] if samples else None, public_sample_count=len(samples))

def state():
    from place_data import provider_status
    with db() as c:
        c.execute('BEGIN')
        return {
            'providers': provider_status(),
            'exploration': exploration_snapshot(c, now()),
            'places': [decorate_place(dict(x)) for x in c.execute('SELECT * FROM places ORDER BY id DESC')],
            'evidence': [dict(x) for x in c.execute('SELECT * FROM evidence ORDER BY id DESC LIMIT 100')],
            'messages': [dict(x) for x in c.execute('SELECT * FROM messages ORDER BY id DESC LIMIT 50')],
            'runs': [dict(x) for x in c.execute('SELECT * FROM runs ORDER BY id DESC LIMIT 20')],
            'location': dict(x) if (x := c.execute('SELECT * FROM locations ORDER BY observed DESC LIMIT 1').fetchone()) else None,
            'settings': dict(c.execute('SELECT * FROM settings WHERE id=1').fetchone()),
        }

def place_context(pid):
    from place_data import public_experiences, fetch_amap_facts
    with db() as c:
        row=c.execute('SELECT * FROM places WHERE id=?',(int(pid),)).fetchone()
        if not row:
            raise ValueError('地点不存在')
        p=dict(row)
        supplied=[dict(x) for x in c.execute('SELECT * FROM experiences WHERE place_id=? ORDER BY id DESC',(int(pid),))]
    return {'place_id':p['id'],'public_experiences':public_experiences(p),'user_experiences':supplied,
            'facts':fetch_amap_facts(p),'live_crowd':None}

def action(path, d):
    if path == '/api/place-context':
        return place_context(d['place_id'])
    if path == '/api/experiences':
        from place_data import validate_experience
        values=validate_experience(d)
        with db() as c:
            pid=int(d['place_id'])
            if not c.execute('SELECT 1 FROM places WHERE id=?',(pid,)).fetchone():
                raise ValueError('地点不存在')
            c.execute('INSERT INTO experiences(place_id,summary,author,platform,url,published,source_type,limitation,created) VALUES(?,?,?,?,?,?,?,?,?)',
                      (pid,values['summary'],values['author'],values['platform'],values['url'],values['published'],values['source_type'],values['limitation'],now()))
        return {'ok':True}

    if path == '/api/demo-xintiandi':
        return enable_xintiandi_demo()
    if path == '/api/pulse':
        return evaluate('page-open', True)
    if path == '/api/chat':
        from language import parse_intent
        utterance = text_field(d, 'text')
        intent = parse_intent(utterance, state()['places'])
        if intent.get('intent') == 'recommend':
            return evaluate('conversation', False)
        if intent.get('intent') == 'feedback':
            if intent.get('kind') == 'later':
                return {'decision': '暂缓需要具体到期时间，请在地点卡片点“稍后”选择时长；未更改记录。'}
            action('/api/feedback', intent)
            return {'decision': '已按你的原话更新记忆'}
        return {'decision': str(intent.get('question', '请明确地点和你想做的事'))[:500]}
    if path == '/api/start-exploration':
        with db() as c:
            current = exploration_snapshot(c, now())
            result = next((x for x in current['recommendations'] if x['place']['id'] == int(d['place_id'])), None)
            if result is None:
                raise ValueError('该地点已不符合当前时间、位置或反馈条件，请重新选择')
            return result
    if path == '/api/evaluate':
        return evaluate('user', False)
    if path == '/api/check':
        return evaluate('manual-trigger', True)
    with db() as c:
        if path == '/api/places':
            raw_lat, raw_lon = d.get('lat'), d.get('lon')
            has_lat, has_lon = raw_lat not in (None, ''), raw_lon not in (None, '')
            if has_lat != has_lon:
                raise ValueError('坐标需要同时填写纬度与经度，或全部留空')
            lat = finite_number(raw_lat, -90, 90, 'lat') if has_lat else None
            lon = finite_number(raw_lon, -180, 180, 'lon') if has_lon else None
            name, source = text_field(d, 'name', 200), text_field(d, 'source', 500)
            category = text_field(d, 'category', 100)
            note = str(d.get('note', ''))[:1000]
            t = now()
            # User-supplied evidence expires conservatively; refresh requires new evidence.
            cur = c.execute('INSERT INTO places(name,lat,lon,category,source,verified,expires,note) VALUES(?,?,?,?,?,?,?,?)', (name, lat, lon, category, source, t, t+7*86400, note))
            c.execute('INSERT INTO evidence(place_id,kind,text,created) VALUES(?,?,?,?)', (cur.lastrowid, 'explicit-interest', note or '用户主动加入想去清单', t))
        elif path == '/api/location':
            lat = finite_number(d['lat'], -90, 90, 'lat')
            lon = finite_number(d['lon'], -180, 180, 'lon')
            accuracy = finite_number(d['accuracy'], 0, 100000, 'accuracy')
            c.execute('INSERT INTO locations(lat,lon,accuracy,observed) VALUES(?,?,?,?)', (lat, lon, accuracy, now()))
            c.execute('DELETE FROM locations WHERE observed<?', (now()-30*86400,))
        elif path == '/api/settings':
            if not isinstance(d.get('proactive'), bool):
                raise ValueError('proactive 必须为布尔值')
            minutes = int(finite_number(d['minutes'], 20, 480, 'minutes'))
            c.execute('UPDATE settings SET proactive=?,minutes=? WHERE id=1', (int(d['proactive']), minutes))
        elif path == '/api/feedback':
            pid = int(d['place_id'])
            p = c.execute('SELECT * FROM places WHERE id=?', (pid,)).fetchone()
            if not p:
                raise ValueError('地点不存在')
            kind = d.get('kind')
            if kind not in ('visited', 'dislike', 'later', 'correction', 'undo-dislike', 'undo-later'):
                raise ValueError('未知反馈类型')
            detail = text_field(d, 'text')
            until = None
            if kind == 'later':
                until = finite_number(d.get('snoozed_until'), now()+1, now()+366*86400, '暂缓到期时间')
            if kind == 'undo-dislike' and p['interest_state'] != 'disliked':
                raise ValueError('该地点没有待撤销的不感兴趣记录')
            if kind == 'undo-later' and not p['snoozed_until']:
                raise ValueError('该地点没有暂缓记录')
            c.execute('INSERT INTO evidence(place_id,kind,text,created,snoozed_until) VALUES(?,?,?,?,?)', (pid, kind, detail, now(), until))
            if kind == 'visited':
                c.execute('UPDATE places SET visited=1,wanted=0,snoozed_until=NULL WHERE id=?', (pid,))
            elif kind == 'dislike':
                c.execute("UPDATE places SET interest_state='disliked' WHERE id=?", (pid,))
            elif kind == 'undo-dislike':
                c.execute("UPDATE places SET interest_state='active' WHERE id=?", (pid,))
            elif kind == 'later':
                c.execute('UPDATE places SET snoozed_until=? WHERE id=?', (until, pid))
            elif kind == 'undo-later':
                c.execute('UPDATE places SET snoozed_until=NULL WHERE id=?', (pid,))
            if kind in ('visited', 'dislike', 'later'):
                c.execute("UPDATE messages SET status=? WHERE place_id=?", (kind, pid))
        elif path == '/api/place-location':
            pid = int(d['place_id'])
            lat = finite_number(d['lat'], -90, 90, 'lat')
            lon = finite_number(d['lon'], -180, 180, 'lon')
            if not c.execute('SELECT 1 FROM places WHERE id=?', (pid,)).fetchone():
                raise ValueError('地点不存在')
            source = text_field(d, 'source', 500)
            c.execute('UPDATE places SET lat=?,lon=?,source=?,verified=?,expires=? WHERE id=?', (lat, lon, source, now(), now()+7*86400, pid))
            c.execute('INSERT INTO evidence(place_id,kind,text,created) VALUES(?,?,?,?)', (pid, 'location-confirmed', source, now()))
        elif path == '/api/refresh':
            pid = int(d['place_id'])
            source = text_field(d, 'source', 500)
            if not c.execute('SELECT 1 FROM places WHERE id=?', (pid,)).fetchone():
                raise ValueError('地点不存在')
            c.execute('UPDATE places SET source=?,verified=?,expires=? WHERE id=?', (source, now(), now()+7*86400, pid))
            c.execute('INSERT INTO evidence(place_id,kind,text,created) VALUES(?,?,?,?)', (pid, 'refresh', source, now()))
        elif path == '/api/delete-data':
            for table in ('experiences', 'places', 'evidence', 'locations', 'messages', 'runs'):
                c.execute('DELETE FROM '+table)
            c.execute('UPDATE settings SET proactive=0 WHERE id=1')
        else:
            raise ValueError('未知操作')
    return evaluate('location', True) if path == '/api/location' else {'ok': True}

class Handler(BaseHTTPRequestHandler):
    def respond(self, status, data, content_type='application/json; charset=utf-8'):
        body = json.dumps(data, ensure_ascii=False).encode() if isinstance(data, (dict, list)) else data
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == '/api/state':
            return self.respond(200, state())
        files = {'/': ('index.html', 'text/html; charset=utf-8'), '/app.js': ('app.js', 'text/javascript; charset=utf-8'), '/map.js': ('map.js', 'text/javascript; charset=utf-8'), '/world.js': ('world.js', 'text/javascript; charset=utf-8'), '/style.css': ('style.css', 'text/css; charset=utf-8')}
        if path not in files:
            return self.respond(404, {'error': '不存在'})
        name, mime = files[path]
        self.respond(200, (ROOT/'static'/name).read_bytes(), mime)

    def do_POST(self):
        # Reject browser cross-origin writes, including DNS rebinding Host values.
        host = self.headers.get('Host', '')
        if host not in ('127.0.0.1:'+str(self.server.server_port), 'localhost:'+str(self.server.server_port)):
            return self.respond(403, {'error': '非法 Host'})
        origin = self.headers.get('Origin')
        if origin and origin not in ('http://'+host,):
            return self.respond(403, {'error': '跨域请求被拒绝'})
        if self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
            return self.respond(415, {'error': '需要 JSON'})
        try:
            n = int(self.headers.get('Content-Length', '0'))
            if not 0 < n <= 16384:
                raise ValueError('请求过大或为空')
            d = json.loads(self.rfile.read(n))
            if not isinstance(d, dict):
                raise ValueError('需要 JSON 对象')
            self.respond(200, action(urlparse(self.path).path, d))
        except (ValueError, KeyError, TypeError, OverflowError) as e:
            self.respond(400, {'error': str(e)})

def scheduler(stop):
    while not stop.wait(60):
        try:
            evaluate()
        except Exception:
            import logging
            logging.exception('Scheduled evaluation failed')

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()
    initialize()
    stop = threading.Event()
    threading.Thread(target=scheduler, args=(stop,), daemon=True).start()
    server = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    print(f'Wander running at http://127.0.0.1:{args.port}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        server.server_close()

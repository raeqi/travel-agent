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
        CREATE TABLE IF NOT EXISTS places(id INTEGER PRIMARY KEY, name TEXT NOT NULL, lat REAL NOT NULL, lon REAL NOT NULL, category TEXT NOT NULL, source TEXT NOT NULL, verified REAL NOT NULL, expires REAL NOT NULL, wanted INTEGER DEFAULT 1, visited INTEGER DEFAULT 0, note TEXT DEFAULT '');
        CREATE TABLE IF NOT EXISTS evidence(id INTEGER PRIMARY KEY, place_id INTEGER, kind TEXT NOT NULL, text TEXT NOT NULL, created REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS locations(id INTEGER PRIMARY KEY, lat REAL NOT NULL, lon REAL NOT NULL, accuracy REAL NOT NULL, observed REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS messages(id INTEGER PRIMARY KEY, place_id INTEGER, text TEXT NOT NULL, created REAL NOT NULL, status TEXT DEFAULT 'new');
        CREATE TABLE IF NOT EXISTS runs(id INTEGER PRIMARY KEY, trigger TEXT NOT NULL, decision TEXT NOT NULL, created REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS settings(id INTEGER PRIMARY KEY CHECK(id=1), proactive INTEGER DEFAULT 0, minutes INTEGER DEFAULT 60, cooldown INTEGER DEFAULT 21600);
        INSERT OR IGNORE INTO settings(id) VALUES(1);
        ''')
        for table, column, definition in (
            ('places', 'origin', "TEXT NOT NULL DEFAULT 'user'"),
            ('locations', 'simulated', 'INTEGER NOT NULL DEFAULT 0'),
            ('locations', 'label', "TEXT NOT NULL DEFAULT ''"),
        ):
            if column not in [r['name'] for r in c.execute('PRAGMA table_info('+table+')')]:
                c.execute('ALTER TABLE '+table+' ADD COLUMN '+column+' '+definition)

def enable_xintiandi_demo():
    from nearby import PLACES
    with db() as c:
        t = now()
        c.execute("INSERT INTO locations(lat,lon,accuracy,observed,simulated,label) VALUES(31.2197,121.4752,100,?,1,'上海 · 新天地附近')", (t,))
        c.execute('UPDATE settings SET proactive=1 WHERE id=1')
        for p in PLACES:
            if not c.execute("SELECT 1 FROM places WHERE name=? AND origin='nearby'", (p['name'],)).fetchone():
                c.execute("INSERT INTO places(name,lat,lon,category,source,verified,expires,wanted,note,origin) VALUES(?,?,?,?,?,?,?,0,?,'nearby')",
                          (p['name'],p['lat'],p['lon'],p['category'],p['source'],t,t+7*86400,p['note']))
    return evaluate('simulated-location', True)

def distance(a, b, x, y):
    r = math.pi / 180
    h = math.sin((x-a)*r/2)**2 + math.cos(a*r)*math.cos(x*r)*math.sin((y-b)*r/2)**2
    return 6371000 * 2 * math.asin(min(1, math.sqrt(h)))

def finite_number(value, low, high, field):
    if isinstance(value, bool):
        raise ValueError(field + ' 必须是数字')
    v = float(value)
    if not math.isfinite(v) or not low <= v <= high:
        raise ValueError(field + ' 超出范围')
    return v

def text_field(data, key, limit=1000):
    s = str(data.get(key, '')).strip()
    if not s or len(s) > limit:
        raise ValueError(key + ' 为空或过长')
    return s

def evaluate(trigger='timer', proactive=True):
    """Atomic decision + delivery: timer and location requests cannot double-send."""
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        t = now()
        s = c.execute('SELECT * FROM settings WHERE id=1').fetchone()
        loc = c.execute('SELECT * FROM locations ORDER BY observed DESC LIMIT 1').fetchone()
        reason = None
        if proactive and not s['proactive']:
            reason = '主动建议未开启'
        elif not loc or t-loc['observed'] > 1800:
            reason = '位置缺失或已超过 30 分钟，等待新位置'
        elif loc['accuracy'] > 200:
            reason = '定位精度不足，保持安静'
        elif proactive and c.execute('SELECT 1 FROM messages WHERE created>? LIMIT 1', (t-s['cooldown'],)).fetchone():
            reason = '处于通知冷却期'
        candidates = []
        if not reason:
            for p in c.execute("SELECT * FROM places WHERE visited=0 AND (wanted=1 OR origin='nearby') AND NOT EXISTS (SELECT 1 FROM evidence WHERE evidence.place_id=places.id AND evidence.kind='dislike')"):
                if p['expires'] < t:
                    continue
                if c.execute("SELECT 1 FROM messages WHERE place_id=? AND created>?", (p['id'], t-7*86400)).fetchone() and proactive:
                    continue
                meters = distance(loc['lat'], loc['lon'], p['lat'], p['lon'])
                if p['origin'] == 'nearby' and meters > 2000:
                    continue
                walking = math.ceil(meters / 65)
                # Straight-line estimate, include return and at least 20 minutes at venue.
                if walking*2+20 <= s['minutes']:
                    candidates.append((walking, dict(p)))
            candidates.sort(key=lambda x: x[0])
            if not candidates:
                reason = '没有信息有效且在可用时间内的待探索地点'
        result = []
        for walking, p in candidates[:1 if proactive else 3]:
            prefix = '你想去的' if p['wanted'] else '我发现'
            msg = f"{prefix}「{p['name']}」在附近，单程步行粗估 {walking} 分钟（直线距离估算，非导航路线）。{p['note']} 信息来源：{p['source']}。营业状态尚未核实，出发前请确认。"
            result.append({'place': p, 'walking_minutes_estimate': walking, 'text': msg})
            if proactive:
                c.execute('INSERT INTO messages(place_id,text,created) VALUES(?,?,?)', (p['id'], msg, t))
        decision = reason or ('已发送主动建议' if proactive else f'返回 {len(result)} 个候选')
        c.execute('INSERT INTO runs(trigger,decision,created) VALUES(?,?,?)', (trigger, decision, t))
        return {'decision': decision, 'recommendations': result}

def state():
    with db() as c:
        return {
            'places': [dict(x) for x in c.execute('SELECT * FROM places ORDER BY id DESC')],
            'evidence': [dict(x) for x in c.execute('SELECT * FROM evidence ORDER BY id DESC LIMIT 100')],
            'messages': [dict(x) for x in c.execute('SELECT * FROM messages ORDER BY id DESC LIMIT 50')],
            'runs': [dict(x) for x in c.execute('SELECT * FROM runs ORDER BY id DESC LIMIT 20')],
            'location': dict(x) if (x := c.execute('SELECT * FROM locations ORDER BY observed DESC LIMIT 1').fetchone()) else None,
            'settings': dict(c.execute('SELECT * FROM settings WHERE id=1').fetchone()),
        }

def action(path, d):
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
            action('/api/feedback', intent)
            return {'decision': '已按你的原话更新记忆'}
        return {'decision': str(intent.get('question', '请明确地点和你想做的事'))[:500]}
    if path == '/api/evaluate':
        return evaluate('user', False)
    if path == '/api/check':
        return evaluate('manual-trigger', True)
    with db() as c:
        if path == '/api/places':
            lat = finite_number(d['lat'], -90, 90, 'lat')
            lon = finite_number(d['lon'], -180, 180, 'lon')
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
            if not c.execute('SELECT 1 FROM places WHERE id=?', (pid,)).fetchone():
                raise ValueError('地点不存在')
            kind = d.get('kind')
            if kind not in ('visited', 'dislike', 'later', 'correction'):
                raise ValueError('未知反馈类型')
            detail = text_field(d, 'text')
            c.execute('INSERT INTO evidence(place_id,kind,text,created) VALUES(?,?,?,?)', (pid, kind, detail, now()))
            if kind == 'visited':
                c.execute('UPDATE places SET visited=1,wanted=0 WHERE id=?', (pid,))
            elif kind == 'dislike':
                c.execute('UPDATE places SET wanted=0 WHERE id=?', (pid,))
            c.execute("UPDATE messages SET status=? WHERE place_id=?", (kind, pid))
        elif path == '/api/refresh':
            pid = int(d['place_id'])
            source = text_field(d, 'source', 500)
            if not c.execute('SELECT 1 FROM places WHERE id=?', (pid,)).fetchone():
                raise ValueError('地点不存在')
            c.execute('UPDATE places SET source=?,verified=?,expires=? WHERE id=?', (source, now(), now()+7*86400, pid))
            c.execute('INSERT INTO evidence(place_id,kind,text,created) VALUES(?,?,?,?)', (pid, 'refresh', source, now()))
        elif path == '/api/delete-data':
            for table in ('places', 'evidence', 'locations', 'messages', 'runs'):
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
        files = {'/': ('index.html', 'text/html; charset=utf-8'), '/app.js': ('app.js', 'text/javascript; charset=utf-8'), '/style.css': ('style.css', 'text/css; charset=utf-8')}
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

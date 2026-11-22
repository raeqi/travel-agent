"""Launch the actual loopback HTTP server against an isolated synthetic database."""
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, build_opener, ProxyHandler

ROOT = Path(__file__).resolve().parents[1]


class HttpSmokeTests(unittest.TestCase):
    def test_loopback_server_shared_budget_and_feedback_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            with socket.socket() as sock:
                sock.bind(('127.0.0.1', 0)); port = sock.getsockname()[1]
            env = dict(os.environ, WANDER_DB=str(Path(tmp)/'http-test.db'), AMAP_WEB_SERVICE_KEY='', WANDER_MODEL='')
            process = subprocess.Popen([sys.executable, str(ROOT/'app.py'), '--port', str(port)], cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            opener = build_opener(ProxyHandler({}))
            base = f'http://127.0.0.1:{port}'
            def request(path, body=None, headers=None):
                h = {'Content-Type':'application/json', **(headers or {})}
                req = Request(base+path, data=json.dumps(body).encode() if body is not None else None, headers=h)
                with opener.open(req, timeout=3) as response:
                    return response.headers, response.read()
            def call(path, body=None): return json.loads(request(path,body)[1])
            try:
                for _ in range(100):
                    if process.poll() is not None: self.fail('loopback service exited before readiness')
                    try: call('/api/state'); break
                    except URLError: time.sleep(.02)
                else: self.fail('loopback service did not become ready')
                self.assertEqual(call('/api/state')['exploration']['recommendations'], [])
                _, html = request('/')
                self.assertIn('试用', (ROOT/'static/app.js').read_text())
                self.assertIn('data-demo', html.decode())
                call('/api/places',dict(name='HTTP合成咖啡',category='咖啡',lat=31.223,lon=121.4752,source='合成测试，不是真实POI'))
                call('/api/settings',dict(proactive=True,minutes=30))
                call('/api/location',dict(lat=31.2197,lon=121.4752,accuracy=10))
                self.assertEqual(call('/api/state')['exploration']['recommendations'], [])
                self.assertEqual(call('/api/evaluate',{})['recommendations'], [])
                call('/api/settings',dict(proactive=True,minutes=35))
                result = call('/api/evaluate',{})['recommendations']
                self.assertEqual(result[0]['total_minutes_estimate'],32)
                pid = result[0]['place']['id']
                self.assertEqual(call('/api/start-exploration',dict(place_id=pid))['place']['id'],pid)
                call('/api/feedback',dict(place_id=pid,kind='later',text='HTTP合成暂缓',snoozed_until=time.time()+3600))
                self.assertEqual(call('/api/state')['exploration']['recommendations'],[])
                self.assertEqual(call('/api/check',{})['recommendations'],[])
                call('/api/feedback',dict(place_id=pid,kind='undo-later',text='HTTP合成恢复'))
                call('/api/feedback',dict(place_id=pid,kind='dislike',text='HTTP合成拒绝'))
                self.assertEqual(call('/api/state')['exploration']['recommendations'],[])
                call('/api/feedback',dict(place_id=pid,kind='undo-dislike',text='HTTP合成撤销拒绝'))
                self.assertEqual(call('/api/state')['exploration']['recommendations'][0]['place']['id'],pid)
                call('/api/places',dict(name='HTTP未定位愿望',category='书店',source='合成测试',note='不填坐标'))
                unlocated=call('/api/state')['places'][0]
                self.assertIsNone(unlocated['lat']); self.assertIsNone(unlocated['lon'])
                with self.assertRaises(HTTPError) as error:
                    request('/api/settings',dict(proactive=True,minutes=60),{'Origin':'https://example.invalid'})
                self.assertEqual(error.exception.code,403)
            finally:
                process.terminate()
                try: process.wait(timeout=3)
                except subprocess.TimeoutExpired: process.kill(); process.wait()

if __name__=='__main__': unittest.main()

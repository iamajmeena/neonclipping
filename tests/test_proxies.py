import importlib
import json
import os
import socket
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

_tmp = tempfile.TemporaryDirectory()
os.environ['NEONCLIPPING_NO_AUTOUPDATE'] = '1'
os.environ['NEONCLIPPING_DATA_DIR'] = _tmp.name
for _k in ('NEONCLIPPING_PROXY', 'NEONCLIPPING_PROXY_MODE', 'NEONCLIPPING_PROXY_COUNTRY', 'NEONCLIPPING_PROXY_GITHUB', 'NEONCLIPPING_PROXY_ROTATE'):
    os.environ.pop(_k, None)

import proxies
import ytdl


class FakeYTProxy:
    rule = None
    calls = []

    def __init__(self, options):
        self.options = dict(options)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def extract_info(self, url, download=True, **kw):
        FakeYTProxy.calls.append(self.options)
        return FakeYTProxy.rule(self.options)

    def download(self, urls):
        FakeYTProxy.calls.append(self.options)
        return FakeYTProxy.rule(self.options)


class ParseAndValidationTests(unittest.TestCase):
    def test_normalize_and_redact_proxy(self):
        self.assertEqual(proxies.normalize_proxy('1.2.3.4:8080'), 'http://1.2.3.4:8080')
        self.assertEqual(proxies.normalize_proxy('SOCKS5://user:sec@10.20.30.40:1080/foo'), 'socks5://user:sec@10.20.30.40:1080')
        self.assertEqual(proxies.redact_proxy('socks5://user:sec@10.20.30.40:1080'), 'socks5://***@10.20.30.40:1080')
        self.assertIsNone(proxies.normalize_proxy('ftp://1.2.3.4:21'))
        self.assertIsNone(proxies.normalize_proxy('http://1.2.3.4:99999'))

    def test_validate_source_url_blocks_ssrf(self):
        self.assertTrue(proxies.validate_source_url('https://raw.githubusercontent.com/proxifly/free-proxy-list/main/proxies/countries/IN/data.json'))
        for bad in (
            'http://raw.githubusercontent.com/a/b.txt',
            'https://127.0.0.1/p.txt',
            'https://192.168.1.10/p.txt',
            'https://localhost/p.txt',
            'file:///etc/passwd',
        ):
            self.assertIsNone(proxies.validate_source_url(bad), bad)

    def test_parse_github_json_and_txt_with_country_filter(self):
        proxifly_json = json.dumps([
            {'proxy': 'socks5://103.1.2.3:1080', 'protocol': 'socks5', 'geolocation': {'country': 'IN'}},
            {'proxy': 'https://103.1.2.4:443', 'protocol': 'https', 'geolocation': {'country': 'IN'}},
            {'proxy': 'http://103.1.2.5:8080', 'protocol': 'http', 'geolocation': {'country': 'IN'}},
            {'proxy': 'http://8.8.8.8:8080', 'protocol': 'http', 'geolocation': {'country': 'US'}},
        ])
        res_in = proxies.parse_remote_payload(proxifly_json, country='IN')
        self.assertEqual(res_in, ['socks5://103.1.2.3:1080', 'http://103.1.2.5:8080'])

        monosans_json = json.dumps([
            {'protocol': 'socks5', 'host': '103.9.9.9', 'port': 1080, 'geolocation': {'country': {'iso_code': 'IN'}}},
            {'protocol': 'socks5', 'host': '1.1.1.1', 'port': 1080, 'geolocation': {'country': {'iso_code': 'SG'}}},
        ])
        self.assertEqual(proxies.parse_remote_payload(monosans_json, country='IN'), ['socks5://103.9.9.9:1080'])

        txt = "45.1.1.1:1080\n# comment\nsocks4://45.2.2.2:4145\n"
        self.assertEqual(
            proxies.parse_remote_payload(txt, source_url='https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/socks5.txt', country='ALL'),
            ['socks5://45.1.1.1:1080', 'socks4://45.2.2.2:4145'],
        )

    def test_infer_country(self):
        self.assertEqual(proxies.infer_country('ERROR: [youtube] x: The uploader has not made this video available in your country This video is available in India.'), 'IN')
        self.assertEqual(proxies.infer_country('This video is available in United States.'), 'US')

    def test_http_connect_tunnel_probe_rejects_404_and_accepts_200(self):
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.bind(('127.0.0.1', 0))
        srv.listen(2)
        port = srv.getsockname()[1]

        def serve():
            for reply in (b'HTTP/1.1 404 Not Found\r\n\r\n', b'HTTP/1.1 200 Connection Established\r\n\r\n'):
                c, _ = srv.accept()
                c.recv(512)
                c.sendall(reply)
                c.close()
            srv.close()

        threading.Thread(target=serve, daemon=True).start()
        self.assertIsNone(proxies._tcp_alive(f'http://127.0.0.1:{port}', timeout=2.0))
        self.assertEqual(proxies._tcp_alive(f'http://127.0.0.1:{port}', timeout=2.0), f'http://127.0.0.1:{port}')

    def test_filter_alive_ranks_fastest_tls_proxy_first(self):
        latencies = {'http://slow:80': (1.4, 'http://slow:80'), 'socks4://fast:1080': (0.2, 'socks4://fast:1080'), 'http://dead:80': None}
        with mock.patch.object(proxies, '_https_alive', side_effect=lambda p, **kw: latencies[p]):
            ranked = proxies.filter_alive(['http://slow:80', 'http://dead:80', 'socks4://fast:1080'], limit=3, max_results=5)
        self.assertEqual(ranked, ['socks4://fast:1080', 'http://slow:80'])


class RotationAndBridgeTests(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.TemporaryDirectory()
        self.data = Path(self.d.name)
        FakeYTProxy.calls = []
        self.p_data = mock.patch.object(ytdl, 'DATA', self.data)
        self.p_yt = mock.patch.object(ytdl.yt_dlp, 'YoutubeDL', FakeYTProxy)
        self.p_tcp = mock.patch.object(proxies, 'filter_alive', side_effect=lambda cands, **kw: list(cands))
        self.p_data.start()
        self.p_yt.start()
        self.p_tcp.start()
        self.addCleanup(self.p_data.stop)
        self.addCleanup(self.p_yt.stop)
        self.addCleanup(self.p_tcp.stop)
        self.addCleanup(self.d.cleanup)
        self.addCleanup(lambda: proxies.clear_cache(self.data))

    def test_geo_block_rotates_github_proxies_without_leaking_cookies(self):
        cookie_file = self.data / 'youtube_cookies.txt'
        cookie_file.write_text('# Netscape HTTP Cookie File\n', encoding='utf-8')
        proxies.save_settings(self.data, {
            'proxy_mode': 'fallback',
            'proxy_github': True,
            'proxy_country': 'IN',
            'proxy_auto_rotate': True,
        })
        sample_json = json.dumps([
            {'proxy': 'http://103.10.10.1:8080', 'protocol': 'http', 'geolocation': {'country': 'IN'}},
            {'proxy': 'socks5://103.10.10.2:1080', 'protocol': 'socks5', 'geolocation': {'country': 'IN'}},
            {'proxy': 'http://103.10.10.3:3128', 'protocol': 'http', 'geolocation': {'country': 'IN'}},
        ])
        proxies.fetch_github_proxies(self.data, country='IN', force=True, fetcher=lambda u: sample_json if 'proxifly' in u else '[]')

        def rule(opts):
            px = opts.get('proxy')
            if not px:
                raise Exception('ERROR: [youtube] jwttobgA1w0: The uploader has not made this video available in your country This video is available in India.')
            if px == 'socks5://103.10.10.2:1080':
                return {'title': 'Tokyo Revengers - Episode 03 [Hindi dub] | Muse IN'}
            raise Exception('Connection timed out')

        FakeYTProxy.rule = staticmethod(rule)
        res = ytdl.YDL({'quiet': True}).extract_info('https://youtu.be/jwttobgA1w0', download=False)
        self.assertEqual(res['title'], 'Tokyo Revengers - Episode 03 [Hindi dub] | Muse IN')
        # First call was direct (had cookiefile), rotated proxy calls MUST strip cookiefile
        self.assertIn('cookiefile', FakeYTProxy.calls[0])
        proxied_calls = [c for c in FakeYTProxy.calls if c.get('proxy')]
        self.assertTrue(proxied_calls)
        for c in proxied_calls:
            self.assertNotIn('cookiefile', c)
            self.assertNotIn('cookiesfrombrowser', c)
        # Sticky last_good cached for next request
        self.assertEqual(proxies.stats(self.data)['last_good'], 'socks5://103.10.10.2:1080')

    def test_download_ranges_with_socks_uses_local_http_bridge(self):
        proxies.save_settings(self.data, {
            'proxy_mode': 'always',
            'proxy': 'socks5://103.55.55.5:1080',
            'proxy_github': False,
        })
        seen = []

        def rule(opts):
            seen.append(opts.get('proxy'))
            return {'ok': True}

        FakeYTProxy.rule = staticmethod(rule)
        res = ytdl.YDL({'download_ranges': lambda *a: []}).extract_info('https://youtu.be/abc', download=False)
        self.assertEqual(res, {'ok': True})
        self.assertEqual(len(seen), 1)
        self.assertTrue(seen[0].startswith('http://127.0.0.1:'), seen)

    def test_slow_proxy_aborts_and_rotates_to_faster_proxy(self):
        proxies.save_settings(self.data, {
            'proxy_mode': 'always',
            'proxy_github': False,
            'proxy_auto_rotate': True,
            'proxy_list': 'http://slow-proxy:8080\nhttp://fast-proxy:8080',
        })
        now = [100.0]

        def rule(opts):
            px = opts.get('proxy')
            hooks = opts.get('progress_hooks') or []
            if px == 'http://slow-proxy:8080' and hooks:
                hooks[0]({'status': 'downloading', 'downloaded_bytes': 1024, 'total_bytes': 22_000_000, 'speed': 30_000})
                now[0] += 12.0
                hooks[0]({'status': 'downloading', 'downloaded_bytes': 300_000, 'total_bytes': 22_000_000, 'speed': 25_000})
            if px == 'http://fast-proxy:8080':
                return {'title': 'fast-ok'}
            return {'title': 'unexpected'}

        FakeYTProxy.rule = staticmethod(rule)
        with mock.patch.object(ytdl.time, 'monotonic', side_effect=lambda: now[0]):
            res = ytdl.YDL({'quiet': True}).download(['https://youtu.be/jwttobgA1w0'])
        self.assertEqual(res, {'title': 'fast-ok'})
        self.assertEqual(proxies.stats(self.data)['last_good'], 'http://fast-proxy:8080')
        self.assertEqual(proxies.stats(self.data)['bad_cooldown_count'], 1)

    def test_local_proxy_bridge_tunnels_connect_via_socks5(self):
        # Spin up a tiny fake upstream SOCKS5 server + fake echo target
        target = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        target.bind(('127.0.0.1', 0))
        target.listen(1)
        t_port = target.getsockname()[1]

        def target_srv():
            c, _ = target.accept()
            data = c.recv(1024)
            c.sendall(b'ECHO:' + data)
            c.close()
            target.close()

        socks_srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        socks_srv.bind(('127.0.0.1', 0))
        socks_srv.listen(1)
        s_port = socks_srv.getsockname()[1]

        def fake_socks():
            c, _ = socks_srv.accept()
            # Greeting: VER=5, NMETHODS, METHODS -> reply NO AUTH
            ver, n = c.recv(2)
            c.recv(n)
            c.sendall(b'\x05\x00')
            # CONNECT request: VER, CMD, RSV, ATYP, ...
            hdr = c.recv(4)
            atyp = hdr[3]
            if atyp == 1:
                addr = socket.inet_ntoa(c.recv(4))
            elif atyp == 3:
                ln = c.recv(1)[0]
                addr = c.recv(ln).decode()
            else:
                addr = '127.0.0.1'
            port = int.from_bytes(c.recv(2), 'big')
            up = socket.create_connection((addr, port), timeout=5)
            c.sendall(b'\x05\x00\x00\x01\x7f\x00\x00\x01' + port.to_bytes(2, 'big'))
            payload = c.recv(1024)
            up.sendall(payload)
            reply = up.recv(1024)
            c.sendall(reply)
            up.close()
            c.close()
            socks_srv.close()

        threading.Thread(target=target_srv, daemon=True).start()
        threading.Thread(target=fake_socks, daemon=True).start()

        with proxies.LocalProxyBridge(f'socks5://127.0.0.1:{s_port}') as bridge_url:
            host_port = bridge_url.replace('http://', '')
            bh, bp = host_port.split(':')
            with socket.create_connection((bh, int(bp)), timeout=5) as sock:
                sock.sendall(f'CONNECT 127.0.0.1:{t_port} HTTP/1.1\r\nHost: 127.0.0.1:{t_port}\r\n\r\n'.encode())
                resp = sock.recv(1024)
                self.assertIn(b'200 Connection Established', resp)
                sock.sendall(b'hello')
                self.assertEqual(sock.recv(1024), b'ECHO:hello')


class SettingsEndpointTests(unittest.TestCase):
    def test_ytdl_settings_and_refresh_routes(self):
        from fastapi.testclient import TestClient

        with tempfile.TemporaryDirectory() as tmp:
            old_dir = os.environ.get('NEONCLIPPING_DATA_DIR')
            os.environ['NEONCLIPPING_DATA_DIR'] = tmp
            try:
                import app as A
                A = importlib.reload(A)
                with TestClient(A.app) as client:
                    r = client.post('/ytdl/settings', json={
                        'proxy_mode': 'fallback',
                        'proxy_github': True,
                        'proxy_country': 'IN',
                        'proxy_auto_rotate': True,
                        'proxy_list': '103.22.1.2:8080\nsocks5://103.22.1.3:1080',
                        'proxy_sources': ['https://raw.githubusercontent.com/proxifly/free-proxy-list/main/proxies/countries/IN/data.json'],
                    })
                    self.assertEqual(r.status_code, 200, r.text)
                    data = r.json()
                    self.assertTrue(data['proxy_github'])
                    self.assertEqual(data['proxy_country'], 'IN')
                    self.assertEqual(data['proxy_mode'], 'fallback')

                    bad = client.post('/ytdl/settings', json={'proxy_sources': ['http://127.0.0.1/bad']})
                    self.assertEqual(bad.status_code, 400)

                    with mock.patch.object(proxies, '_fetch_url', return_value='[{"proxy":"http://103.50.1.1:8080","protocol":"http","geolocation":{"country":"IN"}}]'), \
                         mock.patch.object(proxies, '_https_alive', side_effect=lambda p, **kw: (0.25, p)):
                        ref = client.post('/ytdl/proxies/refresh', json={'proxy_country': 'IN'})
                    self.assertEqual(ref.status_code, 200, ref.text)
                    self.assertEqual(ref.json()['fetched'], 1)
                    self.assertEqual(ref.json()['alive'], 1)
            finally:
                if old_dir is None:
                    os.environ.pop('NEONCLIPPING_DATA_DIR', None)
                else:
                    os.environ['NEONCLIPPING_DATA_DIR'] = old_dir


if __name__ == '__main__':
    unittest.main()

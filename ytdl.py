"""One place for every YouTube / yt-dlp call, so a "Sign in to confirm you're not a bot" or geo-block does not stop people.

What it does
1. Keeps yt-dlp fresh (YouTube changes often; an old yt-dlp is the most common reason downloads fail). Checked at most once a day.
2. Wraps yt-dlp in YDL, a drop-in for yt_dlp.YoutubeDL. When YouTube answers with the bot check (or a 403/429), it retries with
   other settings instead of failing: your own cookies (only if you set them up), then other YouTube player clients.
3. Optional proxy + GitHub proxy list + auto-rotation (via proxies.py): tries direct first in fallback mode, and rotates through
   working HTTP/SOCKS proxies (without sending user cookies over public pools) when YouTube geo-restricts or blocks the server IP.
4. If everything is blocked it raises ONE short, readable message that says what to do (upload the MP4, use your browser login).

Optional cookies (never read unless you ask for them):
  NEONCLIPPING_COOKIES_BROWSER=chrome|edge|firefox|brave   use the login of that browser on this computer
  NEONCLIPPING_COOKIES_FILE=path\\to\\cookies.txt          a Netscape cookies.txt exported from your browser
  data/youtube_cookies.txt                                 same file, picked up automatically if it exists
  data/ytdl.json                                           {"cookies_browser": "chrome"} instead of environment variables
Set NEONCLIPPING_NO_AUTOUPDATE=1 to turn off the daily yt-dlp update.
"""
from contextlib import nullcontext
from pathlib import Path
import json, os, subprocess, sys, time
import proxies

ROOT = Path(__file__).resolve().parent
DATA = Path(os.environ.get('NEONCLIPPING_DATA_DIR', str(ROOT / 'data')))
UPDATE_EVERY = 24 * 3600

def update_ytdlp(force=False):
    """pip-upgrade yt-dlp (with its YouTube helper extras) at most once a day. Silent and offline-safe."""
    if os.environ.get('NEONCLIPPING_NO_AUTOUPDATE') == '1' and not force:
        return False
    stamp = DATA / '.ytdlp_checked'
    try:
        if not force and time.time() - stamp.stat().st_mtime < UPDATE_EVERY:
            return False
    except OSError:
        pass
    ok = False
    try:
        r = subprocess.run([sys.executable, '-m', 'pip', 'install', '-U', 'yt-dlp[default]', '--quiet',
                            '--disable-pip-version-check', '--retries', '0', '--timeout', '8'],
                           capture_output=True, timeout=120)
        ok = r.returncode == 0
    except (OSError, subprocess.SubprocessError):
        pass
    try:
        DATA.mkdir(parents=True, exist_ok=True)
        stamp.write_text(time.strftime('%Y-%m-%d %H:%M:%S') + (' ok' if ok else ' failed'), encoding='utf-8')
    except OSError:
        pass
    return ok

update_ytdlp()          # must run before yt_dlp is imported so the new version is the one that loads
import yt_dlp

BLOCK_MARKERS = ('not a bot', 'sign in to confirm', 'cookies-from-browser', 'http error 403', 'http error 429', 'too many requests')
GEO_MARKERS = ('not available in your country', 'not made this video available in your country', 'blocked it in your country', 'geo-restricted', 'geo restricted')
PROXY_ERR_MARKERS = (
    'proxyerror', 'socks', 'unable to download api page', 'timed out', 'timeout',
    'connection reset', 'connection refused', 'connection aborted', 'remote end closed',
    'eoferror', 'eof occurred', 'tunnel connection failed', 'certificate verify failed',
    'unable to connect to proxy', 'requested format is not available', 'proxy too slow',
)

class SlowProxyError(RuntimeError):
    """Raised by the download progress watchdog when a public proxy crawls too slowly and backup proxies exist."""

def is_blocked(error):
    text = str(error).lower()
    return any(m in text for m in BLOCK_MARKERS)

def is_geo_blocked(error):
    text = str(error).lower()
    return any(m in text for m in GEO_MARKERS)

def is_proxy_retryable(error):
    text = str(error).lower()
    return is_blocked(error) or is_geo_blocked(error) or any(m in text for m in PROXY_ERR_MARKERS)

def _config(data_dir=None):
    d = Path(data_dir) if data_dir is not None else DATA
    saved = {}
    try:
        saved = json.loads((d / 'ytdl.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        pass
    browser = (os.environ.get('NEONCLIPPING_COOKIES_BROWSER') or saved.get('cookies_browser') or '').strip().lower()
    cookie_file = os.environ.get('NEONCLIPPING_COOKIES_FILE') or saved.get('cookies_file') or str(d / 'youtube_cookies.txt')
    return browser, cookie_file

def js_runtimes():
    """YouTube needs a JavaScript runtime to unlock every video quality. yt-dlp only looks for Deno by default; also allow Node."""
    import shutil
    found = {}
    for name in ('deno', 'node'):
        if shutil.which(name):
            found[name] = {}
    return found


def variants(base):
    """Option sets to try, best first. Each entry is (options, is_default)."""
    runtimes = js_runtimes()
    if runtimes and 'js_runtimes' not in base:
        base = {**base, 'js_runtimes': runtimes}
    browser, cookie_file = _config()
    out = []
    if Path(cookie_file).is_file():
        out.append(({**base, 'cookiefile': cookie_file}, False))
    if browser:
        out.append(({**base, 'cookiesfrombrowser': (browser,)}, False))
    out.append((dict(base), True))
    for clients in (['tv', 'web_safari'], ['ios'], ['mweb']):
        out.append(({**base, 'extractor_args': {'youtube': {'player_client': clients}}}, False))
    return out

def _strip_cookies(base):
    out = dict(base)
    out.pop('cookiefile', None)
    out.pop('cookiesfrombrowser', None)
    return out

GUIDE = ("YouTube blocked this download (its bot check). This happens on shared, mobile-data or VPN internet. Fix, easiest first: "
         "1) Click Upload video and upload the MP4 instead (always works). "
         "2) Sign in to YouTube in Chrome, then set NEONCLIPPING_COOKIES_BROWSER=chrome (Edge or Firefox also work) and restart "
         "(see README: YouTube bot check). "
         "3) Try another network (home Wi-Fi, VPN off), or enable GitHub proxies + auto-rotation under YouTube settings. "
         "The tool already updated its downloader and tried several other YouTube modes.")

class YDL:
    """Drop-in for yt_dlp.YoutubeDL: supports `with YDL(opts) as y: y.extract_info(...)` and `y.download([...])`."""
    def __init__(self, opts=None):
        self.opts = dict(opts or {})

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def _run_with_proxies(self, fn, first_error, inferred_country=None):
        cfg = proxies.config(DATA)
        country = inferred_country if (cfg['proxy_country'] == 'AUTO' and inferred_country) else cfg['proxy_country']
        pool, is_public = proxies.candidates(DATA, country=country)
        if not pool:
            return False, first_error, False
        base = _strip_cookies(self.opts) if is_public else dict(self.opts)
        runtimes = js_runtimes()
        if runtimes and 'js_runtimes' not in base:
            base['js_runtimes'] = runtimes
        max_tries = 18 if cfg['proxy_auto_rotate'] else 1
        last_err = first_error
        blocked = False
        attempt_pool = pool[:max_tries]
        for idx, proxy_url in enumerate(attempt_pool):
            has_backup = idx + 1 < len(attempt_pool)
            use_bridge = bool('download_ranges' in base and proxy_url.startswith(proxies.SOCKS_SCHEMES))
            ctx = proxies.LocalProxyBridge(proxy_url) if use_bridge else nullcontext(proxy_url)
            with ctx as active_proxy:
                opts = {**base, 'proxy': active_proxy}
                if len(pool) > 1:
                    opts['extractor_retries'] = 0
                    if opts.get('skip_download'):
                        opts['retries'] = 0
                        opts['socket_timeout'] = min(float(opts.get('socket_timeout') or 12), 8)
                if is_public and cfg['proxy_auto_rotate'] and has_backup and not opts.get('skip_download'):
                    user_hooks = list(opts.get('progress_hooks') or [])
                    dl_state = {'t0': None, 'b0': 0}

                    def _speed_guard(d, st=dl_state):
                        if d.get('status') == 'downloading':
                            got = d.get('downloaded_bytes') or 0
                            total = d.get('total_bytes') or d.get('total_bytes_estimate') or 0
                            now_t = time.monotonic()
                            if st['t0'] is None:
                                st['t0'] = now_t
                                st['b0'] = got
                            dt = now_t - st['t0']
                            if dt >= 10.0 and (total == 0 or total > 2 * 1024 * 1024):
                                avg = max(0.0, got - st['b0']) / dt
                                cur_speed = d.get('speed')
                                if avg < 90_000 and (cur_speed is None or cur_speed < 100_000):
                                    raise SlowProxyError(f'Proxy too slow ({avg / 1024:.0f} KB/s); rotating to faster proxy.')
                        elif d.get('status') == 'finished':
                            st['t0'] = None

                    opts['progress_hooks'] = user_hooks + [_speed_guard]
                try:
                    with yt_dlp.YoutubeDL(opts) as y:
                        result = fn(y)
                    proxies.mark_good(DATA, proxy_url)
                    return True, result, False
                except Exception as e:      # noqa: BLE001 - retry across proxy pool
                    if is_blocked(e):
                        blocked = True
                    last_err = e
                    proxies.mark_bad(DATA, proxy_url)
                    if not is_proxy_retryable(e):
                        return False, e, blocked
        return False, last_err, blocked

    def _run(self, fn):
        cfg = proxies.config(DATA)
        if 'proxy' not in self.opts and cfg['proxy_mode'] == 'always':
            ok, val, blocked = self._run_with_proxies(fn, None)
            if ok:
                return val
            if val is not None:
                if blocked and not is_geo_blocked(val):
                    raise RuntimeError(GUIDE) from val
                raise val

        blocked = False
        geo_err = None
        first = None
        for options, is_default in variants(self.opts):
            try:
                with yt_dlp.YoutubeDL(options) as y:
                    return fn(y)
            except Exception as e:      # noqa: BLE001 - yt-dlp raises several error types
                first = first or e
                if is_geo_blocked(e):
                    geo_err = e
                    break
                if is_blocked(e):
                    blocked = True
                    continue
                if not is_default:      # cookies unreadable, client unsupported, ...: just try the next way
                    continue
                raise

        if geo_err is not None:
            if 'proxy' not in self.opts and cfg['proxy_mode'] in ('fallback', 'always'):
                ok, val, _ = self._run_with_proxies(fn, geo_err, inferred_country=proxies.infer_country(str(geo_err)))
                if ok:
                    return val
                if val is not None:
                    raise val
            raise geo_err

        if blocked:
            if 'proxy' not in self.opts and cfg['proxy_mode'] in ('fallback', 'always'):
                ok, val, _ = self._run_with_proxies(fn, first)
                if ok:
                    return val
            raise RuntimeError(GUIDE) from first
        raise first

    def extract_info(self, url, download=True, **kw):
        return self._run(lambda y: y.extract_info(url, download=download, **kw))

    def download(self, urls):
        return self._run(lambda y: y.download(urls))

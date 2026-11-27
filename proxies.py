"""Optional YouTube proxy pool, GitHub proxy-list fetcher, TCP health pre-filter, and auto-rotation.

Supports:
- A single user-configured proxy URL (NEONCLIPPING_PROXY or ytdl.json["proxy"])
- A user-pasted proxy list (http/https/socks4/socks5)
- Optional public GitHub open-proxy lists with country filtering (e.g. IN, US, ALL, or AUTO from error text)
- Fast parallel TCP pre-check, sticky last-working proxy, bad-proxy cooldown, and a loopback HTTP CONNECT bridge
  so FFmpeg download_ranges also works when the selected proxy uses SOCKS4/SOCKS5.

Public rotated proxies are always used WITHOUT browser/file cookies so user accounts are never sent over public nodes.
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urlparse, urlunparse
import ipaddress
import json
import os
import random
import re
import select
import socket
import ssl
import threading
import time
import urllib.request

VALID_PROXY_SCHEMES = ('http', 'https', 'socks4', 'socks4a', 'socks5', 'socks5h')
SOCKS_SCHEMES = ('socks4', 'socks4a', 'socks5', 'socks5h')
SUPPORTED_COUNTRIES = ('IN', 'US', 'GB', 'SG', 'DE', 'CA', 'AU', 'JP', 'FR', 'BR', 'AUTO', 'ALL')
CACHE_TTL = 1800          # refresh GitHub raw lists at most every 30 minutes unless requested
ALIVE_TTL = 600           # reuse speed-ranked alive proxy list for 10 minutes
BAD_TTL = 600             # cooldown for proxies that timed out or failed against YouTube
TCP_PROBE_TIMEOUT = 3.0
TCP_PROBE_LIMIT = 400

COUNTRY_ALIASES = {
    'india': 'IN',
    'united states': 'US',
    'usa': 'US',
    'u.s.': 'US',
    'united kingdom': 'GB',
    'uk': 'GB',
    'great britain': 'GB',
    'singapore': 'SG',
    'germany': 'DE',
    'canada': 'CA',
    'australia': 'AU',
    'japan': 'JP',
    'france': 'FR',
    'brazil': 'BR',
}

DEFAULT_GITHUB_SOURCES = [
    'https://raw.githubusercontent.com/proxifly/free-proxy-list/main/proxies/countries/{country}/data.json',
    'https://raw.githubusercontent.com/monosans/proxy-list/main/proxies.json',
]
EXTRA_ALL_GITHUB_SOURCES = [
    'https://raw.githubusercontent.com/proxifly/free-proxy-list/main/proxies/all/data.json',
    'https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt',
    'https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/socks5.txt',
    'https://raw.githubusercontent.com/vakhov/fresh-proxy-list/master/http.txt',
    'https://raw.githubusercontent.com/vakhov/fresh-proxy-list/master/socks5.txt',
]

_LOCK = threading.Lock()
_MEMORY = {}   # key: resolved data_dir str -> {'good': [...], 'bad': {p: ts}, 'lists': {cache_key: {'ts': t, 'proxies': [...]}}}


def _mem(data_dir):
    key = str(Path(data_dir).resolve())
    with _LOCK:
        entry = _MEMORY.get(key)
        if entry is None:
            entry = _load_cache_file(Path(data_dir))
            _MEMORY[key] = entry
        return entry


def _load_cache_file(data_dir):
    p = Path(data_dir) / 'proxy_cache.json'
    try:
        raw = json.loads(p.read_text(encoding='utf-8'))
        if isinstance(raw, dict):
            return {
                'good': [x for x in raw.get('good', []) if isinstance(x, str)][:25],
                'bad': {str(k): float(v) for k, v in (raw.get('bad') or {}).items() if isinstance(v, (int, float))},
                'lists': raw.get('lists') if isinstance(raw.get('lists'), dict) else {},
                'alive': raw.get('alive') if isinstance(raw.get('alive'), dict) else {},
            }
    except (OSError, ValueError, TypeError):
        pass
    return {'good': [], 'bad': {}, 'lists': {}, 'alive': {}}


def _save_cache_file(data_dir, entry):
    try:
        d = Path(data_dir)
        d.mkdir(parents=True, exist_ok=True)
        now = time.time()
        clean = {
            'good': list(entry['good'])[:25],
            'bad': {k: v for k, v in entry['bad'].items() if now - v < BAD_TTL},
            'lists': entry['lists'],
            'alive': entry.get('alive') or {},
        }
        tmp = d / 'proxy_cache.tmp'
        tmp.write_text(json.dumps(clean), encoding='utf-8')
        tmp.replace(d / 'proxy_cache.json')
    except OSError:
        pass


def normalize_proxy(raw, default_scheme='http'):
    """Validate and canonicalize one proxy URL (`scheme://[user:pass@]host:port`). Returns None if invalid."""
    s = str(raw or '').strip()
    if not s or any(c.isspace() for c in s):
        return None
    if '://' not in s:
        s = f'{default_scheme}://{s}'
    try:
        u = urlparse(s)
    except ValueError:
        return None
    scheme = (u.scheme or '').lower()
    if scheme not in VALID_PROXY_SCHEMES:
        return None
    host = (u.hostname or '').strip()
    try:
        port = u.port
    except ValueError:
        return None
    if not host or not port or not (1 <= port <= 65535):
        return None
    auth = ''
    if u.username:
        auth = u.username + (f':{u.password}' if u.password is not None else '') + '@'
    netloc = f'{auth}[{host}]:{port}' if ':' in host else f'{auth}{host}:{port}'
    return urlunparse((scheme, netloc, '', '', '', ''))


def redact_proxy(proxy_url):
    """Mask proxy username/password before returning config to UI."""
    if not proxy_url:
        return ''
    try:
        u = urlparse(proxy_url)
        if not u.username and not u.password:
            return proxy_url
        host = f'[{u.hostname}]' if u.hostname and ':' in u.hostname else (u.hostname or '')
        return f'{u.scheme}://***@{host}:{u.port}'
    except ValueError:
        return proxy_url


def validate_source_url(raw):
    """Validate an HTTPS URL for remote proxy list fetching, blocking private/loopback SSRF targets."""
    s = str(raw or '').strip()
    if not s or any(c.isspace() for c in s):
        return None
    try:
        u = urlparse(s)
    except ValueError:
        return None
    if (u.scheme or '').lower() != 'https':
        return None
    host = (u.hostname or '').strip().lower()
    if not host or host in ('localhost', 'ip6-localhost') or host.endswith(('.local', '.internal', '.localhost')):
        return None
    try:
        ip = ipaddress.ip_address(host)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            return None
    except ValueError:
        pass
    return s


def parse_proxy_text(raw_text, default_scheme='http'):
    """Parse newline/comma/whitespace separated proxy URLs or host:port strings."""
    out = []
    seen = set()
    for token in re.split(r'[\s,;]+', str(raw_text or '').strip()):
        if not token or token.startswith('#'):
            continue
        norm = normalize_proxy(token, default_scheme=default_scheme)
        if norm and norm not in seen:
            seen.add(norm)
            out.append(norm)
    return out


def normalize_country(country):
    c = str(country or 'IN').strip().upper()
    if c in SUPPORTED_COUNTRIES:
        return c
    if len(c) == 2 and c.isalpha():
        return c
    return 'IN'


def infer_country(text):
    """Detect country code mentioned in YouTube geo-block message, e.g. 'available in India' -> 'IN'."""
    low = str(text or '').lower()
    m = re.search(r'available in ([a-z][a-z .]{1,30})', low)
    if m:
        phrase = m.group(1).strip(' .,!?:;')
        for name, code in COUNTRY_ALIASES.items():
            if phrase == name or phrase.startswith(name + ' '):
                return code
    for name, code in COUNTRY_ALIASES.items():
        if re.search(r'\b' + re.escape(name) + r'\b', low):
            return code
    return None


def config(data_dir):
    """Return normalized proxy settings dict from env vars + data/ytdl.json."""
    saved = {}
    try:
        saved = json.loads((Path(data_dir) / 'ytdl.json').read_text(encoding='utf-8'))
    except (OSError, ValueError, TypeError):
        saved = {}
    env_proxy = normalize_proxy(os.environ.get('NEONCLIPPING_PROXY', '')) or ''
    proxy = env_proxy or normalize_proxy(saved.get('proxy', '')) or ''
    proxy_list = str(saved.get('proxy_list') or '')
    env_gh = os.environ.get('NEONCLIPPING_PROXY_GITHUB')
    proxy_github = (env_gh == '1') if env_gh in ('0', '1') else bool(saved.get('proxy_github', False))
    country = normalize_country(os.environ.get('NEONCLIPPING_PROXY_COUNTRY') or saved.get('proxy_country') or 'IN')
    env_rot = os.environ.get('NEONCLIPPING_PROXY_ROTATE')
    auto_rotate = (env_rot == '1') if env_rot in ('0', '1') else bool(saved.get('proxy_auto_rotate', True))
    sources = [s for s in (saved.get('proxy_sources') or []) if validate_source_url(s)]
    raw_mode = (os.environ.get('NEONCLIPPING_PROXY_MODE') or saved.get('proxy_mode') or '').strip().lower()
    if raw_mode in ('off', 'fallback', 'always'):
        mode = raw_mode
    elif env_proxy or proxy or proxy_github or parse_proxy_text(proxy_list):
        mode = 'fallback'
    else:
        mode = 'off'
    return {
        'proxy': proxy,
        'proxy_list': proxy_list,
        'proxy_github': proxy_github,
        'proxy_country': country,
        'proxy_auto_rotate': auto_rotate,
        'proxy_mode': mode,
        'proxy_sources': sources,
    }


def save_settings(data_dir, body):
    """Validate and merge proxy fields into data/ytdl.json, keeping existing browser/cookie keys."""
    d = Path(data_dir)
    path = d / 'ytdl.json'
    try:
        cfg = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(cfg, dict):
            cfg = {}
    except (OSError, ValueError):
        cfg = {}

    if 'proxy' in body:
        raw_p = str(body.get('proxy') or '').strip()
        if raw_p:
            if raw_p != redact_proxy(cfg.get('proxy', '')):
                norm = normalize_proxy(raw_p)
                if not norm:
                    raise ValueError('Proxy must look like http://host:port or socks5://host:port.')
                cfg['proxy'] = norm
        else:
            cfg.pop('proxy', None)

    if 'proxy_list' in body:
        lines = parse_proxy_text(body.get('proxy_list') or '')
        if lines:
            cfg['proxy_list'] = '\n'.join(lines)
        else:
            cfg.pop('proxy_list', None)

    if 'proxy_github' in body:
        cfg['proxy_github'] = bool(body.get('proxy_github'))

    if 'proxy_auto_rotate' in body:
        cfg['proxy_auto_rotate'] = bool(body.get('proxy_auto_rotate'))

    if 'proxy_country' in body:
        cfg['proxy_country'] = normalize_country(body.get('proxy_country'))

    if 'proxy_sources' in body:
        raw_srcs = body.get('proxy_sources')
        if isinstance(raw_srcs, str):
            raw_srcs = [x.strip() for x in re.split(r'[\n,]+', raw_srcs) if x.strip()]
        valid_srcs = []
        for s in (raw_srcs or []):
            v = validate_source_url(s.replace('{country}', 'IN'))
            if not v:
                raise ValueError(f'GitHub / remote proxy list must be a public https:// URL: {s}')
            valid_srcs.append(str(s).strip())
        if valid_srcs:
            cfg['proxy_sources'] = valid_srcs
        else:
            cfg.pop('proxy_sources', None)

    if 'proxy_mode' in body:
        mode = str(body.get('proxy_mode') or '').strip().lower()
        if mode not in ('off', 'fallback', 'always'):
            raise ValueError('Proxy mode must be off, fallback, or always.')
        cfg['proxy_mode'] = mode

    d.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cfg, indent=2), encoding='utf-8')
    return config(data_dir)


def _scheme_from_source(url):
    low = url.lower()
    if 'socks5' in low:
        return 'socks5'
    if 'socks4' in low:
        return 'socks4'
    return 'http'


def parse_remote_payload(body, source_url='', country='ALL'):
    """Parse JSON or plaintext proxy lists from GitHub repositories, filtering by country when available."""
    cc = None if country in ('ALL', 'AUTO', '') else country.upper()
    default_scheme = _scheme_from_source(source_url)
    text = (body or '').strip()
    if not text:
        return []
    out = []
    seen = set()

    def _add(p):
        if p and p not in seen:
            seen.add(p)
            out.append(p)

    if text.startswith('[') or text.startswith('{'):
        try:
            data = json.loads(text)
            if isinstance(data, dict):
                data = data.get('proxies') or data.get('data') or []
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, str):
                        p = normalize_proxy(item, default_scheme=default_scheme)
                        if p and not p.startswith('https://'):
                            _add(p)
                        continue
                    if not isinstance(item, dict):
                        continue
                    geo = item.get('geolocation') or {}
                    item_cc = ''
                    if isinstance(geo.get('country'), dict):
                        item_cc = str(geo['country'].get('iso_code') or '').upper()
                    elif geo.get('country'):
                        item_cc = str(geo.get('country')).upper()
                    elif item.get('country'):
                        item_cc = str(item.get('country')).upper()
                    if cc and item_cc and item_cc != cc:
                        continue
                    proto = str(item.get('protocol') or item.get('type') or '').lower()
                    # Public raw proxy lists label broken MITM/IP-mismatch servers as 'https'; skip them here.
                    if proto == 'https':
                        continue
                    if item.get('proxy'):
                        p = normalize_proxy(item['proxy'], default_scheme=proto or default_scheme)
                    else:
                        host = item.get('ip') or item.get('host')
                        port = item.get('port')
                        if not host or not port:
                            continue
                        auth = ''
                        if item.get('username'):
                            auth = f"{item['username']}:{item.get('password') or ''}@"
                        p = normalize_proxy(f"{proto or default_scheme}://{auth}{host}:{port}")
                    if p and not p.startswith('https://'):
                        _add(p)
                return out
        except ValueError:
            pass

    for p in parse_proxy_text(text, default_scheme=default_scheme):
        if not p.startswith('https://'):
            _add(p)
    return out


def _effective_sources(cfg, country):
    if cfg.get('proxy_sources'):
        out = []
        for s in cfg['proxy_sources']:
            formatted = s.replace('{country}', 'all' if country in ('ALL', 'AUTO') else country)
            if validate_source_url(formatted):
                out.append(formatted)
        return out
    if country in ('ALL', 'AUTO'):
        return list(EXTRA_ALL_GITHUB_SOURCES) + ['https://raw.githubusercontent.com/monosans/proxy-list/main/proxies.json']
    return [s.replace('{country}', country) for s in DEFAULT_GITHUB_SOURCES]


def _fetch_url(url, timeout=10):
    req = urllib.request.Request(url, headers={'User-Agent': 'NeonClipping/1.0'})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read(8 * 1024 * 1024).decode('utf-8', errors='replace')


def _prioritize_protocols(pool):
    """Balance protocols (socks5, http, socks4) so working YouTube tunnels appear early."""
    s5 = [p for p in pool if p.startswith(('socks5://', 'socks5h://'))]
    http = [p for p in pool if p.startswith('http://')]
    s4 = [p for p in pool if p.startswith(('socks4://', 'socks4a://'))]
    rest = [p for p in pool if not p.startswith(('http://', 'socks5://', 'socks5h://', 'socks4://', 'socks4a://'))]
    for grp in (s5, http, s4, rest):
        random.shuffle(grp)
    merged = []
    for i in range(max(len(s5), len(http), len(s4), 0)):
        if i < len(s5):
            merged.append(s5[i])
        if i < len(s4):
            merged.append(s4[i])
        if i < len(http):
            merged.append(http[i])
    return merged + rest


def fetch_github_proxies(data_dir, country='IN', force=False, fetcher=None):
    """Fetch and cache public proxy list from GitHub sources for `country`."""
    cfg = config(data_dir)
    cc = normalize_country(country)
    sources = _effective_sources(cfg, cc)
    cache_key = f"{cc}|{'|'.join(sources)}"
    mem = _mem(data_dir)
    now = time.time()
    with _LOCK:
        cached = mem['lists'].get(cache_key)
        if not force and cached and now - cached.get('ts', 0) < CACHE_TTL and cached.get('proxies'):
            return list(cached['proxies'])

    get = fetcher or _fetch_url
    collected = []
    seen = set()
    for src in sources:
        if not validate_source_url(src):
            continue
        try:
            body = get(src)
            for p in parse_remote_payload(body, source_url=src, country=cc):
                if p not in seen:
                    seen.add(p)
                    collected.append(p)
        except Exception:
            continue

    if collected:
        with _LOCK:
            mem['lists'][cache_key] = {'ts': time.time(), 'proxies': collected}
            _save_cache_file(data_dir, mem)
    elif cached and cached.get('proxies'):
        return list(cached['proxies'])
    return collected


def _open_tunnel(proxy_url, host='www.youtube.com', port=443, timeout=TCP_PROBE_TIMEOUT):
    """Open a socket tunneled through proxy_url to (host, port). Caller owns closing it."""
    s = None
    try:
        u = urlparse(proxy_url)
        scheme = (u.scheme or '').lower()
        if scheme in SOCKS_SCHEMES:
            import socks as pysocks
            stype = pysocks.SOCKS4 if scheme.startswith('socks4') else pysocks.SOCKS5
            s = pysocks.socksocket()
            s.settimeout(timeout)
            s.set_proxy(stype, u.hostname, u.port, rdns=(scheme == 'socks5h'), username=u.username, password=u.password)
            s.connect((host, port))
            return s
        s = socket.create_connection((u.hostname, u.port), timeout=timeout)
        s.settimeout(timeout)
        req = f'CONNECT {host}:{port} HTTP/1.1\r\nHost: {host}:{port}\r\n'
        if u.username:
            import base64
            tok = base64.b64encode(f"{u.username}:{u.password or ''}".encode()).decode()
            req += f'Proxy-Authorization: Basic {tok}\r\n'
        s.sendall((req + '\r\n').encode('latin1'))
        head = s.recv(128).split(b'\r\n', 1)[0]
        if re.match(rb'^HTTP/1\.[01]\s+200\b', head):
            return s
        s.close()
        return None
    except Exception:
        if s is not None:
            try:
                s.close()
            except OSError:
                pass
        return None


def _tcp_alive(proxy_url, timeout=TCP_PROBE_TIMEOUT):
    """Verify the proxy opens a tunnel to www.youtube.com:443."""
    s = _open_tunnel(proxy_url, timeout=timeout)
    if s is None:
        return None
    try:
        s.close()
    except OSError:
        pass
    return proxy_url


_TLS_CTX = ssl.create_default_context()


def _https_alive(proxy_url, timeout=5.5):
    """Verify tunnel + real TLS + YouTube download throughput; returns (sec_per_128kb, proxy_url) sorted fastest first."""
    t0 = time.monotonic()
    deadline = t0 + timeout
    s = _open_tunnel(proxy_url, timeout=min(TCP_PROBE_TIMEOUT, timeout))
    if s is None:
        return None
    tls = None
    try:
        tls = _TLS_CTX.wrap_socket(s, server_hostname='www.youtube.com')
        tls.settimeout(max(0.5, deadline - time.monotonic()))
        tls.sendall(b'GET / HTTP/1.1\r\nHost: www.youtube.com\r\nUser-Agent: Mozilla/5.0\r\nConnection: close\r\n\r\n')
        buf = bytearray()
        body_start = -1
        code = ''
        while time.monotonic() < deadline:
            tls.settimeout(max(0.3, deadline - time.monotonic()))
            chunk = tls.recv(32768)
            if not chunk:
                break
            buf.extend(chunk)
            if body_start < 0:
                idx = buf.find(b'\r\n\r\n')
                if idx >= 0:
                    head = bytes(buf[:idx]).split(b'\r\n', 1)[0]
                    m = re.match(rb'^HTTP/1\.[01]\s+(200|204|30\d)\b', head)
                    if not m:
                        return None
                    code = m.group(1).decode('ascii')
                    body_start = idx + 4
                    if code == '204':
                        break
            if body_start >= 0 and len(buf) - body_start >= 262144:
                break
        if body_start < 0:
            return None
        elapsed = max(0.05, time.monotonic() - t0)
        body_bytes = len(buf) - body_start
        if code == '200' and body_bytes >= 49152:
            # Seconds per 128 KB transferred (lower = higher throughput + lower handshake latency).
            return (round(elapsed / (body_bytes / 131072.0), 3), proxy_url)
        if code != '200':
            return (round(elapsed * 2.5, 3), proxy_url)
        return None
    except Exception:
        return None
    finally:
        for sock in (tls, s):
            if sock is not None:
                try:
                    sock.close()
                except OSError:
                    pass


def filter_alive(candidates, limit=TCP_PROBE_LIMIT, max_results=20):
    """Verify tunnel + TLS/HTTP YouTube throughput in parallel and return fastest proxies first."""
    sample = list(candidates[:limit])
    if not sample:
        return []
    hits = []
    ex = ThreadPoolExecutor(max_workers=min(80, len(sample)))
    futures = [ex.submit(_https_alive, p) for p in sample]
    try:
        for fut in as_completed(futures, timeout=6.5):
            res = fut.result()
            if res:
                hits.append(res)
                if len(hits) >= max_results:
                    break
    except Exception:
        pass
    finally:
        ex.shutdown(wait=False, cancel_futures=True)
    hits.sort(key=lambda item: item[0])
    return [p for _, p in hits]


def candidates(data_dir, country=None, force_refresh=False, probe_tcp=True, fetcher=None):
    """Return ordered list of proxy URLs to try for rotation:
    1. User's explicit single proxy (always trusted first if set)
    2. Recently working sticky proxies ('good')
    3. User's custom proxy_list (bandwidth-probed if probe_tcp)
    4. GitHub fetched proxies for the chosen country (bandwidth-probed if probe_tcp & cached)
    Returns (list_of_proxies, includes_public_pool_bool).
    """
    cfg = config(data_dir)
    cc = normalize_country(country or cfg['proxy_country'])
    if cc == 'AUTO':
        cc = 'IN'
    mem = _mem(data_dir)
    now = time.time()
    with _LOCK:
        bad = {k for k, ts in mem['bad'].items() if now - ts < BAD_TTL}
        good = [p for p in mem['good'] if p not in bad]
        alive_entry = (mem.get('alive') or {}).get(cc)

    manual_single = [cfg['proxy']] if cfg['proxy'] else []
    custom_list = [p for p in parse_proxy_text(cfg['proxy_list']) if p not in bad and p not in manual_single]
    remote_list = []
    if cfg['proxy_github']:
        raw_remote = fetch_github_proxies(data_dir, country=cc, force=force_refresh, fetcher=fetcher)
        remote_list = [p for p in _prioritize_protocols(raw_remote) if p not in bad and p not in manual_single and p not in custom_list]

    uses_public_pool = bool(cfg['proxy_github'] or custom_list)
    if not cfg['proxy_auto_rotate']:
        out = []
        for p in manual_single + good + custom_list + remote_list:
            if p not in out:
                out.append(p)
        return out[:1], uses_public_pool

    pool = custom_list + remote_list
    if probe_tcp and pool:
        cached_alive = []
        if not force_refresh and alive_entry and now - alive_entry.get('ts', 0) < ALIVE_TTL:
            pool_set = set(pool)
            cached_alive = [p for p in alive_entry.get('proxies', []) if p in pool_set and p not in bad]
        if len(cached_alive) >= 2:
            pool = cached_alive
        else:
            probed = filter_alive(pool)
            if probed:
                pool = probed
                with _LOCK:
                    mem.setdefault('alive', {})[cc] = {'ts': time.time(), 'proxies': list(probed)}
                    _save_cache_file(data_dir, mem)

    ordered = []
    seen = set()
    for p in manual_single + good + pool:
        if p and p not in seen:
            seen.add(p)
            ordered.append(p)
    return ordered, uses_public_pool


def refresh_pool(data_dir, country='IN'):
    """Fetch fresh GitHub proxies for `country`, benchmark YouTube throughput across the pool, and cache fastest first."""
    cc = 'IN' if normalize_country(country) == 'AUTO' else normalize_country(country)
    raw = fetch_github_proxies(data_dir, country=cc, force=True)
    alive = filter_alive(_prioritize_protocols(raw), limit=TCP_PROBE_LIMIT, max_results=20)
    mem = _mem(data_dir)
    with _LOCK:
        mem.setdefault('alive', {})[cc] = {'ts': time.time(), 'proxies': list(alive)}
        _save_cache_file(data_dir, mem)
    return raw, alive


def mark_good(data_dir, proxy_url):
    if not proxy_url:
        return
    mem = _mem(data_dir)
    with _LOCK:
        mem['bad'].pop(proxy_url, None)
        mem['good'] = [proxy_url] + [p for p in mem['good'] if p != proxy_url]
        mem['good'] = mem['good'][:25]
        _save_cache_file(data_dir, mem)


def mark_bad(data_dir, proxy_url):
    if not proxy_url:
        return
    mem = _mem(data_dir)
    with _LOCK:
        mem['bad'][proxy_url] = time.time()
        mem['good'] = [p for p in mem['good'] if p != proxy_url]
        for entry in (mem.get('alive') or {}).values():
            if isinstance(entry, dict) and isinstance(entry.get('proxies'), list):
                entry['proxies'] = [p for p in entry['proxies'] if p != proxy_url]
        _save_cache_file(data_dir, mem)


def stats(data_dir):
    cfg = config(data_dir)
    mem = _mem(data_dir)
    now = time.time()
    with _LOCK:
        good = [redact_proxy(p) for p in mem['good']]
        bad_count = sum(1 for ts in mem['bad'].values() if now - ts < BAD_TTL)
        cached_count = sum(len(v.get('proxies') or []) for v in mem['lists'].values())
    return {
        'cached_count': cached_count,
        'good_count': len(good),
        'bad_cooldown_count': bad_count,
        'last_good': good[0] if good else None,
        'mode': cfg['proxy_mode'],
    }


def clear_cache(data_dir):
    key = str(Path(data_dir).resolve())
    with _LOCK:
        _MEMORY.pop(key, None)
        try:
            (Path(data_dir) / 'proxy_cache.json').unlink(missing_ok=True)
        except OSError:
            pass


class LocalProxyBridge:
    """Tiny loopback HTTP CONNECT bridge so FFmpeg can tunnel through SOCKS4/SOCKS5 proxies."""

    def __init__(self, upstream_proxy):
        self.upstream = upstream_proxy
        self._srv = None
        self._stop = threading.Event()
        self._thread = None
        self.url = None

    def __enter__(self):
        u = urlparse(self.upstream)
        scheme = (u.scheme or '').lower()
        if scheme not in SOCKS_SCHEMES:
            self.url = self.upstream
            return self.url
        import socks as pysocks
        stype = pysocks.SOCKS4 if scheme.startswith('socks4') else pysocks.SOCKS5
        rdns = scheme == 'socks5h'
        up_host, up_port = u.hostname, u.port
        up_user, up_pass = u.username, u.password

        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind(('127.0.0.1', 0))
        srv.listen(32)
        srv.settimeout(0.5)
        self._srv = srv
        port = srv.getsockname()[1]
        self.url = f'http://127.0.0.1:{port}'

        def _tunnel(client, remote):
            try:
                sockets = [client, remote]
                while not self._stop.is_set():
                    r, _, _ = select.select(sockets, [], [], 2.0)
                    if not r:
                        continue
                    for s in r:
                        data = s.recv(65536)
                        if not data:
                            return
                        (remote if s is client else client).sendall(data)
            except OSError:
                pass
            finally:
                for s in (client, remote):
                    try:
                        s.close()
                    except OSError:
                        pass

        def _handle(client):
            remote = None
            try:
                client.settimeout(10)
                buf = b''
                while b'\r\n\r\n' not in buf and len(buf) < 16384:
                    chunk = client.recv(4096)
                    if not chunk:
                        client.close()
                        return
                    buf += chunk
                head = buf.split(b'\r\n', 1)[0].decode('latin1', errors='replace')
                parts = head.split()
                if len(parts) < 2 or parts[0].upper() != 'CONNECT' or ':' not in parts[1]:
                    client.sendall(b'HTTP/1.1 400 Bad Request\r\n\r\n')
                    client.close()
                    return
                dst_host, dst_port_s = parts[1].rsplit(':', 1)
                dst_host = dst_host.strip('[]')
                dst_port = int(dst_port_s)
                remote = pysocks.socksocket()
                remote.settimeout(12)
                remote.set_proxy(stype, up_host, up_port, rdns=rdns, username=up_user, password=up_pass)
                remote.connect((dst_host, dst_port))
                client.sendall(b'HTTP/1.1 200 Connection Established\r\n\r\n')
                client.settimeout(60)
                remote.settimeout(60)
                rest = buf.split(b'\r\n\r\n', 1)[1]
                if rest:
                    remote.sendall(rest)
                _tunnel(client, remote)
            except Exception:
                try:
                    client.sendall(b'HTTP/1.1 502 Bad Gateway\r\n\r\n')
                except OSError:
                    pass
                for s in (client, remote):
                    if s is not None:
                        try:
                            s.close()
                        except OSError:
                            pass

        def _serve():
            while not self._stop.is_set():
                try:
                    client, _ = srv.accept()
                except socket.timeout:
                    continue
                except OSError:
                    break
                threading.Thread(target=_handle, args=(client,), daemon=True).start()

        self._thread = threading.Thread(target=_serve, daemon=True)
        self._thread.start()
        return self.url

    def __exit__(self, *exc):
        self._stop.set()
        if self._srv is not None:
            try:
                self._srv.close()
            except OSError:
                pass
        if self._thread is not None:
            self._thread.join(timeout=1.5)
        return False

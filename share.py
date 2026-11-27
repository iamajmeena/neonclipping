"""Optional on-demand Cloudflare Tunnel sharing (only installed and started when the user asks)."""
import os
import platform
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import threading
import time
from pathlib import Path
from urllib.request import Request, urlopen

from fastapi import HTTPException, Request as FastAPIRequest

import phone

URL_RE = re.compile(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com")
_lock = threading.RLock()
_state = {
    "proc": None,
    "url": "",
    "error": "",
    "installing": False,
    "reader": None,
}


def _bin_dir(data):
    return Path(data) / "bin"


def _bin_name():
    return "cloudflared.exe" if sys.platform == "win32" else "cloudflared"


def find_cloudflared(data):
    local = _bin_dir(data) / _bin_name()
    if local.is_file():
        return str(local)
    return shutil.which("cloudflared")


def _download_spec():
    sys_name = platform.system().lower()
    arch = platform.machine().lower()
    if arch in ("x86_64", "amd64"):
        arch_tag = "amd64"
    elif arch in ("aarch64", "arm64"):
        arch_tag = "arm64"
    elif arch.startswith("armv7") or arch == "arm":
        arch_tag = "arm"
    else:
        raise ValueError(f"Unsupported CPU architecture for automatic cloudflared install: {arch}")

    base = "https://github.com/cloudflare/cloudflared/releases/latest/download/"
    if sys_name == "linux":
        return base + f"cloudflared-linux-{arch_tag}", "raw"
    if sys_name == "windows":
        if arch_tag != "amd64":
            return base + "cloudflared-windows-386.exe", "raw"
        return base + "cloudflared-windows-amd64.exe", "raw"
    if sys_name == "darwin":
        if arch_tag not in ("arm64", "amd64"):
            raise ValueError(f"Unsupported macOS architecture: {arch}")
        return base + f"cloudflared-darwin-{arch_tag}.tgz", "tgz"
    raise ValueError(f"Unsupported operating system for automatic cloudflared install: {sys_name}")


def install_cloudflared(data):
    """Download the official cloudflared binary into data/bin/ after explicit user confirmation."""
    with _lock:
        if _state["installing"]:
            raise ValueError("Cloudflare installation is already running.")
        _state["installing"] = True
    try:
        existing = find_cloudflared(data)
        if existing:
            return existing
        url, kind = _download_spec()
        bin_dir = _bin_dir(data)
        bin_dir.mkdir(parents=True, exist_ok=True)
        dest = bin_dir / _bin_name()
        tmp = bin_dir / (_bin_name() + ".tmp")
        dl = bin_dir / "cloudflared-download.tmp"
        req = Request(url, headers={"User-Agent": "NeonClipping"})
        try:
            with urlopen(req, timeout=90) as resp, dl.open("wb") as out:
                shutil.copyfileobj(resp, out)
            if kind == "tgz":
                with tarfile.open(dl, "r:gz") as tf:
                    member = next((m for m in tf.getmembers() if m.isfile() and os.path.basename(m.name) == "cloudflared"), None)
                    if not member:
                        raise ValueError("Downloaded archive did not contain cloudflared.")
                    src = tf.extractfile(member)
                    if src is None:
                        raise ValueError("Could not extract cloudflared.")
                    with src, tmp.open("wb") as out:
                        shutil.copyfileobj(src, out)
            else:
                dl.replace(tmp)
            if sys.platform != "win32":
                tmp.chmod(tmp.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
            proc = subprocess.run([str(tmp), "--version"], capture_output=True, text=True, timeout=15)
            if proc.returncode != 0:
                raise ValueError("Downloaded cloudflared binary failed verification.")
            tmp.replace(dest)
            return str(dest)
        except Exception as error:
            tmp.unlink(missing_ok=True)
            raise ValueError(f"Could not install Cloudflare Tunnel: {error}") from error
        finally:
            dl.unlink(missing_ok=True)
    finally:
        with _lock:
            _state["installing"] = False


def _is_running():
    proc = _state.get("proc")
    return proc is not None and proc.poll() is None


def status(data, port="8770"):
    with _lock:
        running = _is_running()
        if not running and _state.get("proc") is not None:
            _state["proc"] = None
            _state["url"] = ""
        binary = find_cloudflared(data)
        return {
            "installed": bool(binary),
            "binary": binary or "",
            "installing": bool(_state["installing"]),
            "running": running,
            "url": _state["url"] if running else "",
            "base_url": _state["url"] if running else "",
            "error": _state.get("error") or "",
            "port": str(port),
            "pin_required": phone.pin_enabled(),
        }


def stop_tunnel():
    with _lock:
        proc = _state.get("proc")
        _state["proc"] = None
        _state["url"] = ""
        _state["error"] = ""
    if proc is not None and proc.poll() is None:
        try:
            proc.terminate()
            proc.wait(timeout=4)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
    return {"running": False, "url": ""}


def start_tunnel(data, port="8770"):
    with _lock:
        if _is_running():
            return status(data, port)
        binary = find_cloudflared(data)
        if not binary:
            raise FileNotFoundError("Cloudflare Tunnel (cloudflared) is not installed yet.")
        _state["url"] = ""
        _state["error"] = ""
        cmd = [binary, "tunnel", "--no-autoupdate", "--url", f"http://127.0.0.1:{port}"]
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            errors="replace",
        )
        _state["proc"] = proc

    def reader():
        lines = []
        try:
            if proc.stdout:
                for line in proc.stdout:
                    lines.append(line.strip())
                    if len(lines) > 30:
                        lines.pop(0)
                    match = URL_RE.search(line)
                    if match:
                        with _lock:
                            if _state.get("proc") is proc:
                                _state["url"] = match.group(0)
        except Exception:
            pass
        finally:
            with _lock:
                if _state.get("proc") is proc and proc.poll() not in (None, 0):
                    _state["error"] = (lines[-1] if lines else "Cloudflare tunnel exited unexpectedly.")[:240]

    threading.Thread(target=reader, daemon=True, name="cloudflared-reader").start()
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        with _lock:
            if _state.get("url"):
                break
            if proc.poll() is not None:
                if not _state.get("error"):
                    _state["error"] = "Cloudflare tunnel could not start."
                break
        time.sleep(0.25)
    return status(data, port)


def attach(app, data, root):
    def port_of(request):
        return os.environ.get("NEONCLIPPING_PORT") or str(request.url.port or 8770)

    def require_local(request: FastAPIRequest):
        if phone.pin_enabled() and not phone.is_local_request(request):
            raise HTTPException(403, "Share controls are only available on the PC.")
        origin = request.headers.get("origin")
        if origin and origin != str(request.base_url).rstrip("/"):
            raise HTTPException(403, "Share controls must be opened from this app.")

    @app.get("/share/status")
    def share_status(request: FastAPIRequest):
        require_local(request)
        return status(data, port_of(request))

    @app.post("/share/install")
    def share_install(body: dict, request: FastAPIRequest):
        require_local(request)
        if body.get("confirm") is not True:
            raise HTTPException(400, "Ask the user to confirm before installing Cloudflare Tunnel.")
        try:
            install_cloudflared(data)
            return status(data, port_of(request))
        except ValueError as error:
            raise HTTPException(400, str(error)) from error

    @app.post("/share/start")
    def share_start(request: FastAPIRequest):
        require_local(request)
        if not phone.lan_enabled():
            raise HTTPException(400, "Device access is disabled (NEONCLIPPING_LAN=0).")
        try:
            return start_tunnel(data, port_of(request))
        except FileNotFoundError as error:
            raise HTTPException(409, {"message": str(error), "needs_install": True}) from error
        except Exception as error:
            raise HTTPException(500, str(error)) from error

    @app.post("/share/stop")
    def share_stop(request: FastAPIRequest):
        require_local(request)
        stop_tunnel()
        return status(data, port_of(request))

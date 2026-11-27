"""Optional direct publishing and auto-upload queue. Tokens stay local."""
import json
import math
from contextlib import contextmanager
import os
from pathlib import Path
import sqlite3
import threading
import time
import uuid
from urllib.parse import urlparse

from fastapi import HTTPException
import requests

from social_accounts import PROVIDERS, access_token as token
from timeline import media_path

YT = "https://www.googleapis.com/youtube/v3"
IG = "https://graph.instagram.com/v26.0"
TT = "https://open.tiktokapis.com/v2"
X = "https://api.x.com/2"
FB = "https://graph.facebook.com/v21.0"
FB_VIDEO = "https://graph-video.facebook.com/v21.0"
LI = "https://api.linkedin.com"
TH = "https://graph.threads.net/v1.0"

PLATFORMS = ("youtube", "x", "instagram", "facebook", "tiktok", "linkedin", "threads", "custom")
PLATFORM_INFO = {
    "youtube": {
        "label": "YouTube",
        "auth": "oauth",
        "requires_media_url": False,
        "max_title": 100,
        "default_privacy": "public",
        "privacy": ["private", "unlisted", "public"],
    },
    "x": {
        "label": "X (Twitter)",
        "auth": "oauth",
        "requires_media_url": False,
        "max_title": 280,
        "default_privacy": "everyone",
        "privacy": ["everyone", "following", "mentionedUsers"],
    },
    "instagram": {
        "label": "Instagram",
        "auth": "oauth",
        "requires_media_url": True,
        "max_title": 2200,
        "default_privacy": "account visibility",
        "privacy": ["account visibility"],
    },
    "facebook": {
        "label": "Facebook",
        "auth": "oauth",
        "requires_media_url": False,
        "max_title": 2200,
        "default_privacy": "public",
        "privacy": ["public", "friends", "only_me"],
    },
    "tiktok": {
        "label": "TikTok",
        "auth": "oauth",
        "requires_media_url": False,
        "max_title": 2200,
        "default_privacy": "SELF_ONLY",
        "privacy": [],
    },
    "linkedin": {
        "label": "LinkedIn",
        "auth": "oauth",
        "requires_media_url": False,
        "max_title": 3000,
        "default_privacy": "public",
        "privacy": ["public", "connections"],
    },
    "threads": {
        "label": "Threads",
        "auth": "oauth",
        "requires_media_url": True,
        "max_title": 500,
        "default_privacy": "public",
        "privacy": ["public", "following", "mentioned"],
    },
    "custom": {
        "label": "More platforms (Custom upload)",
        "auth": "custom",
        "requires_media_url": False,
        "max_title": 2200,
        "default_privacy": "public",
        "privacy": ["public", "unlisted", "private"],
    },
}

AUTO_SOURCES = ("make", "live", "export")
AUTO_DEFAULTS = {
    "enabled": False,
    "platforms": [],
    "platform_privacy": {},
    "sources": ["make", "live"],
    "draft_only": False,
    "min_score": 0,
    "skip_flagged": True,
    "gap_minutes": 30,
    "daily_cap": 4,
    "offset_minutes": 0,
    "include_hashtags": True,
    "media_base_url": "",
    "custom_url": "",
    "custom_token": "",
}
_auto_lock = threading.RLock()
_ctx = {"data": None}


def _auto_file(data):
    return Path(data) / "preferences" / "auto_upload.json"


def _validate_endpoint_url(url, label="URL", allow_template=False):
    value = str(url or "").strip()
    if not value:
        return ""
    probe = value.replace("{clip}", "0" * 32) if allow_template else value
    parsed = urlparse(probe)
    local = (parsed.hostname or "").lower() in ("127.0.0.1", "localhost")
    if (
        parsed.scheme not in ("https", "http")
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or (parsed.scheme == "http" and not local)
        or len(value) > 400
    ):
        raise ValueError(f"{label}: use an https address (http only for localhost).")
    return value


def read_auto_upload(data=None):
    data = data or _ctx.get("data")
    if not data:
        return dict(AUTO_DEFAULTS)
    try:
        raw = json.loads(_auto_file(data).read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        raw = {}
    if not isinstance(raw, dict):
        raw = {}
    return {**AUTO_DEFAULTS, **raw}


def public_auto_upload(data=None):
    cfg = read_auto_upload(data)
    has_token = bool(cfg.get("custom_token") or os.getenv("NEONCLIPPING_CUSTOM_TOKEN"))
    out = {k: v for k, v in cfg.items() if k != "custom_token"}
    out["has_custom_token"] = has_token
    return out


def validate_auto_upload(body, current=None):
    if not isinstance(body, dict):
        raise ValueError("Provide auto-upload settings.")
    base = dict(current or AUTO_DEFAULTS)
    out = {}
    if "enabled" in body:
        out["enabled"] = bool(body.get("enabled"))
    if "platforms" in body:
        items = body.get("platforms") or []
        if not isinstance(items, list):
            raise ValueError("Platforms must be a list.")
        clean = []
        for item in items:
            p = str(item or "").strip().lower()
            if p not in PLATFORMS:
                raise ValueError(f"Unsupported platform: {p}.")
            if p not in clean:
                clean.append(p)
        out["platforms"] = clean
    if "platform_privacy" in body:
        mapping = body.get("platform_privacy") or {}
        if not isinstance(mapping, dict):
            raise ValueError("Platform visibility settings must be a map.")
        out["platform_privacy"] = {str(k).lower(): str(v) for k, v in mapping.items() if str(k).lower() in PLATFORMS and v}
    if "sources" in body:
        items = body.get("sources") or []
        if not isinstance(items, list):
            raise ValueError("Sources must be a list.")
        out["sources"] = [str(s).lower() for s in items if str(s).lower() in AUTO_SOURCES]
    if "draft_only" in body:
        out["draft_only"] = bool(body.get("draft_only"))
    if "min_score" in body:
        score = int(body.get("min_score") or 0)
        if not 0 <= score <= 100:
            raise ValueError("Minimum viral score must be between 0 and 100.")
        out["min_score"] = score
    if "skip_flagged" in body:
        out["skip_flagged"] = bool(body.get("skip_flagged"))
    if "gap_minutes" in body:
        minutes = int(body.get("gap_minutes") or 0)
        if not 0 <= minutes <= 1440:
            raise ValueError("Minutes between posts must be between 0 and 1440.")
        out["gap_minutes"] = minutes
    if "daily_cap" in body:
        cap = int(body.get("daily_cap") or 0)
        if not 0 <= cap <= 24:
            raise ValueError("Daily post limit must be between 0 and 24.")
        out["daily_cap"] = cap
    if "offset_minutes" in body:
        offset = int(body.get("offset_minutes") or 0)
        if not -720 <= offset <= 840:
            raise ValueError("Timezone offset is out of range.")
        out["offset_minutes"] = offset
    if "include_hashtags" in body:
        out["include_hashtags"] = bool(body.get("include_hashtags"))
    if "media_base_url" in body:
        val = _validate_endpoint_url(body.get("media_base_url"), "Hosted media URL", allow_template=True)
        if val and not val.startswith("https://"):
            raise ValueError("Hosted media URL for Instagram / Threads must start with https://.")
        out["media_base_url"] = val
    if "custom_url" in body:
        out["custom_url"] = _validate_endpoint_url(body.get("custom_url"), "Custom upload URL")
    if "clear_custom_token" in body and body.get("clear_custom_token"):
        out["custom_token"] = ""
    elif "custom_token" in body:
        tok = str(body.get("custom_token") or "").strip()
        if tok:
            out["custom_token"] = tok[:500]
    merged = {**base, **out}
    if merged.get("enabled") and not merged.get("platforms"):
        raise ValueError("Select at least one platform for auto-upload.")
    return out


def save_auto_upload(data, body):
    with _auto_lock:
        current = read_auto_upload(data)
        cfg = {**current, **validate_auto_upload(body, current)}
        target = _auto_file(data)
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(".tmp")
        tmp.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(target)
    return public_auto_upload(data)


def _custom_endpoint(data=None):
    cfg = read_auto_upload(data)
    url = (os.getenv("NEONCLIPPING_CUSTOM_UPLOAD_URL") or cfg.get("custom_url") or "").strip()
    url = _validate_endpoint_url(url, "Custom upload URL")
    if not url:
        raise ValueError("Set a Custom upload URL in Auto-upload settings or NEONCLIPPING_CUSTOM_UPLOAD_URL.")
    tok = (os.getenv("NEONCLIPPING_CUSTOM_TOKEN") or cfg.get("custom_token") or "").strip()
    return url, tok


def call(method, url, platform=None, **kwargs):
    headers = kwargs.pop("headers", {})
    if platform:
        headers = {**headers, "Authorization": "Bearer " + token(platform)}
    try:
        response = requests.request(method, url, headers=headers, timeout=(10, 120), allow_redirects=False, **kwargs)
    except requests.RequestException:
        raise ValueError("Platform connection failed. Check the post on the platform before retrying.") from None
    if not 200 <= response.status_code < 300:
        raise ValueError(f"Platform returned HTTP {response.status_code}. Check authorization, post settings and platform history.")
    return response


def tt(path, body):
    result = call("POST", TT + path, "tiktok", json=body).json()
    if result.get("error", {}).get("code") != "ok":
        raise ValueError("TikTok declined the request: " + str(result.get("error", {}).get("code", "unknown"))[:80])
    return result["data"]


def _fb_page(platform, preferred_id=None):
    try:
        res = call("GET", FB + "/me/accounts", platform, params={"fields": "id,name,access_token"}).json()
        pages = res.get("data") if isinstance(res, dict) else None
    except ValueError:
        pages = None
    if isinstance(pages, list) and pages:
        chosen = next((p for p in pages if preferred_id and str(p.get("id")) == str(preferred_id)), pages[0])
        return str(chosen["id"]), str(chosen.get("name") or chosen["id"]), chosen.get("access_token")
    if preferred_id:
        return str(preferred_id), str(preferred_id), None
    me = call("GET", FB + "/me", platform, params={"fields": "id,name"}).json()
    return str(me["id"]), str(me.get("name") or me["id"]), None


def account(platform):
    if platform == "youtube":
        items = call("GET", YT + "/channels", platform, params={"part": "snippet", "mine": "true"}).json()["items"]
        if not items:
            raise ValueError("No YouTube channel is connected.")
        return {"id": items[0]["id"], "name": items[0]["snippet"]["title"], "privacy": ["private", "unlisted", "public"]}
    if platform == "x":
        row = call("GET", X + "/users/me", platform).json()["data"]
        name = ("@" + row["username"]) if row.get("username") else row.get("name", row["id"])
        return {"id": str(row["id"]), "name": name, "privacy": ["everyone", "following", "mentionedUsers"]}
    if platform == "instagram":
        row = call("GET", IG + "/me", platform, params={"fields": "user_id,username"}).json()
        return {"id": str(row["user_id"]), "name": row["username"], "privacy": ["account visibility"]}
    if platform == "facebook":
        page_id, page_name, _ = _fb_page(platform)
        return {"id": page_id, "name": page_name, "privacy": ["public", "friends", "only_me"]}
    if platform == "tiktok":
        row = tt("/post/publish/creator_info/query/", {})
        return {
            "id": row["creator_username"],
            "name": row["creator_nickname"],
            "privacy": row["privacy_level_options"],
            "max_duration": row["max_video_post_duration_sec"],
        }
    if platform == "linkedin":
        row = call("GET", LI + "/v2/userinfo", platform).json()
        return {"id": str(row["sub"]), "name": row.get("name") or str(row["sub"]), "privacy": ["public", "connections"]}
    if platform == "threads":
        row = call("GET", TH + "/me", platform, params={"fields": "id,username"}).json()
        return {"id": str(row["id"]), "name": row.get("username") or str(row["id"]), "privacy": ["public", "following", "mentioned"]}
    if platform == "custom":
        url, _ = _custom_endpoint()
        host = urlparse(url).hostname or "custom"
        return {"id": host, "name": f"Custom upload ({host})", "privacy": ["public", "unlisted", "private"]}
    raise ValueError("Choose a supported platform.")


def upload_url(value, hosts):
    parsed = urlparse(value)
    if parsed.scheme != "https" or parsed.username or parsed.hostname not in hosts:
        raise ValueError("Platform returned an unexpected upload destination.")
    return value


def publish(row, data):
    platform = row["platform"]
    acct = account(platform)
    if acct["id"] != row["account"] or row["privacy"] not in acct["privacy"]:
        raise ValueError("The destination account or visibility choices changed.")
    media = media_path(data, row["clip"])
    size = media.stat().st_size

    if platform == "youtube":
        desc = (row.get("description") or row["title"])[:5000]
        response = call(
            "POST",
            "https://www.googleapis.com/upload/youtube/v3/videos",
            platform,
            params={"uploadType": "resumable", "part": "snippet,status"},
            headers={"X-Upload-Content-Length": str(size), "X-Upload-Content-Type": "video/mp4"},
            json={"snippet": {"title": row["title"][:100], "description": desc}, "status": {"privacyStatus": row["privacy"]}},
        )
        dest = upload_url(response.headers["Location"], {"www.googleapis.com", "youtube.googleapis.com"})
        with media.open("rb") as file:
            return call("PUT", dest, platform, data=file, headers={"Content-Type": "video/mp4"}).json()["id"]

    if platform == "x":
        init = call(
            "POST",
            X + "/media/upload/initialize",
            platform,
            json={"total_bytes": size, "media_type": "video/mp4", "media_category": "tweet_video"},
        ).json()
        init_data = init.get("data") if isinstance(init.get("data"), dict) else init
        media_id = str(init_data.get("id") or init.get("media_id_string"))
        chunk_size = 4 * 1024 * 1024
        with media.open("rb") as file:
            idx = 0
            while True:
                chunk = file.read(chunk_size)
                if not chunk:
                    break
                call(
                    "POST",
                    f"{X}/media/upload/{media_id}/append",
                    platform,
                    data={"segment_index": str(idx)},
                    files={"media": ("clip.mp4", chunk, "video/mp4")},
                )
                idx += 1
        fin = call("POST", f"{X}/media/upload/{media_id}/finalize", platform).json()
        fin_data = fin.get("data") if isinstance(fin.get("data"), dict) else fin
        info = fin_data.get("processing_info")
        for _ in range(60):
            if not info or info.get("state") == "succeeded":
                break
            if info.get("state") == "failed":
                raise ValueError("X could not process this video.")
            time.sleep(min(10, max(1, int(info.get("check_after_secs", 3)))))
            status_res = call("GET", X + "/media/upload", platform, params={"command": "STATUS", "media_id": media_id}).json()
            status_data = status_res.get("data") if isinstance(status_res.get("data"), dict) else status_res
            info = status_data.get("processing_info")
        else:
            raise ValueError("X timed out processing the video.")
        tweet = {"text": row["title"][:280], "media": {"media_ids": [media_id]}}
        if row["privacy"] in ("following", "mentionedUsers"):
            tweet["reply_settings"] = row["privacy"]
        posted = call("POST", X + "/tweets", platform, json=tweet).json()
        post_data = posted.get("data") if isinstance(posted.get("data"), dict) else posted
        return str(post_data["id"])

    if platform == "instagram":
        source = row["media_url"]
        if not source.startswith("https://"):
            raise ValueError("Instagram requires the public HTTPS URL of this exact export.")
        endpoint = IG + "/" + acct["id"]
        container = call("POST", endpoint + "/media", platform, data={"media_type": "REELS", "video_url": source, "caption": row["title"]}).json()["id"]
        for _ in range(60):
            status = call("GET", IG + "/" + container, platform, params={"fields": "status_code"}).json()["status_code"]
            if status == "FINISHED":
                break
            if status in ("ERROR", "EXPIRED"):
                raise ValueError("Instagram could not prepare this Reel.")
            time.sleep(5)
        else:
            raise ValueError("Instagram timed out preparing the Reel.")
        return call("POST", endpoint + "/media_publish", platform, data={"creation_id": container}).json()["id"]

    if platform == "facebook":
        page_id, _, page_token = _fb_page(platform, acct["id"])
        fb_kwargs = {"headers": {"Authorization": "Bearer " + page_token}} if page_token else {}
        fb_plat = None if page_token else platform
        start_res = call(
            "POST",
            f"{FB_VIDEO}/{page_id}/videos",
            fb_plat,
            data={"upload_phase": "start", "file_size": str(size)},
            **fb_kwargs,
        ).json()
        session_id = str(start_res["upload_session_id"])
        start_off = int(start_res.get("start_offset", 0))
        end_off = int(start_res.get("end_offset", size))
        with media.open("rb") as file:
            while start_off < end_off:
                file.seek(start_off)
                chunk = file.read(end_off - start_off)
                if not chunk:
                    break
                step = call(
                    "POST",
                    f"{FB_VIDEO}/{page_id}/videos",
                    fb_plat,
                    data={"upload_phase": "transfer", "upload_session_id": session_id, "start_offset": str(start_off)},
                    files={"video_file_chunk": ("clip.mp4", chunk, "video/mp4")},
                    **fb_kwargs,
                ).json()
                next_start = int(step.get("start_offset", end_off))
                next_end = int(step.get("end_offset", size))
                if next_start <= start_off and next_end <= end_off:
                    break
                start_off, end_off = next_start, next_end
        privacy_map = {"public": "EVERYONE", "friends": "ALL_FRIENDS", "only_me": "SELF"}
        fin = call(
            "POST",
            f"{FB_VIDEO}/{page_id}/videos",
            fb_plat,
            data={
                "upload_phase": "finish",
                "upload_session_id": session_id,
                "title": row["title"][:255],
                "description": (row.get("description") or row["title"])[:5000],
                "privacy": json.dumps({"value": privacy_map.get(row["privacy"], "EVERYONE")}),
            },
            **fb_kwargs,
        ).json()
        return str(fin.get("id") or fin.get("video_id") or session_id)

    if platform == "linkedin":
        li_headers = {"LinkedIn-Version": "202411", "X-Restli-Protocol-Version": "2.0.0"}
        init = call(
            "POST",
            LI + "/rest/videos?action=initializeUpload",
            platform,
            headers=li_headers,
            json={
                "initializeUploadRequest": {
                    "owner": f"urn:li:person:{acct['id']}",
                    "fileSizeBytes": size,
                    "uploadCaptions": False,
                    "uploadThumbnail": False,
                }
            },
        ).json()["value"]
        video_urn = init["video"]
        etags = []
        with media.open("rb") as file:
            for part in init["uploadInstructions"]:
                dest = upload_url(
                    part["uploadUrl"],
                    {"www.linkedin.com", "api.linkedin.com", "dms.licdn.com", "dms-uploads.licdn.com"},
                )
                first_b, last_b = int(part["firstByte"]), int(part["lastByte"])
                file.seek(first_b)
                chunk = file.read(last_b - first_b + 1)
                up = call("PUT", dest, data=chunk, headers={"Content-Type": "application/octet-stream"})
                etag = (getattr(up, "headers", None) or {}).get("ETag") or (getattr(up, "headers", None) or {}).get("etag") or ""
                if etag:
                    etags.append(etag)
        call(
            "POST",
            LI + "/rest/videos?action=finalizeUpload",
            platform,
            headers=li_headers,
            json={"finalizeUploadRequest": {"video": video_urn, "uploadToken": "", "uploadedPartIds": etags}},
        )
        vis = "CONNECTIONS" if row["privacy"] == "connections" else "PUBLIC"
        post = call(
            "POST",
            LI + "/rest/posts",
            platform,
            headers=li_headers,
            json={
                "author": f"urn:li:person:{acct['id']}",
                "commentary": row["title"][:3000],
                "visibility": vis,
                "distribution": {"feedDistribution": "MAIN_FEED", "targetEntities": [], "thirdPartyDistributionChannels": []},
                "content": {"media": {"title": row["title"][:200], "id": video_urn}},
                "lifecycleState": "PUBLISHED",
                "isReshareDisabledByAuthor": False,
            },
        )
        post_id = (getattr(post, "headers", None) or {}).get("x-restli-id")
        if not post_id:
            try:
                post_id = (post.json() or {}).get("id")
            except (ValueError, TypeError):
                post_id = None
        return str(post_id or video_urn)

    if platform == "threads":
        source = row["media_url"]
        if not source.startswith("https://"):
            raise ValueError("Threads requires the public HTTPS URL of this exact export.")
        endpoint = TH + "/" + acct["id"]
        reply_ctrl = {"public": "everyone", "following": "accounts_you_follow", "mentioned": "mentioned_only"}.get(row["privacy"], "everyone")
        container = call(
            "POST",
            endpoint + "/threads",
            platform,
            data={"media_type": "VIDEO", "video_url": source, "text": row["title"][:500], "reply_control": reply_ctrl},
        ).json()["id"]
        for _ in range(60):
            status = call("GET", TH + "/" + container, platform, params={"fields": "status"}).json().get("status")
            if status == "FINISHED":
                break
            if status in ("ERROR", "EXPIRED"):
                raise ValueError("Threads could not prepare this video.")
            time.sleep(5)
        else:
            raise ValueError("Threads timed out preparing the video.")
        return str(call("POST", endpoint + "/threads_publish", platform, data={"creation_id": container}).json()["id"])

    if platform == "custom":
        url, custom_tok = _custom_endpoint(data)
        headers = {"User-Agent": "NeonClipping"}
        if custom_tok:
            headers["Authorization"] = "Bearer " + custom_tok
        with media.open("rb") as file:
            res = call(
                "POST",
                url,
                None,
                headers=headers,
                data={
                    "clip": row["clip"],
                    "title": row["title"],
                    "privacy": row["privacy"],
                    "platform": "custom",
                    "description": row.get("description", ""),
                    "hashtags": json.dumps(row.get("hashtags") or []),
                },
                files={"video": (media.name, file, "video/mp4")},
            )
        try:
            body = res.json()
            if isinstance(body, dict) and (body.get("id") or body.get("post_id")):
                return str(body.get("id") or body.get("post_id"))
        except ValueError:
            pass
        return "custom-" + row["clip"][:12]

    chunk = min(size, 16 * 1024 * 1024)
    count = size // chunk
    response = tt(
        "/post/publish/video/init/",
        {
            "post_info": {
                "title": row["title"],
                "privacy_level": row["privacy"],
                "disable_comment": True,
                "disable_duet": True,
                "disable_stitch": True,
                "brand_content_toggle": row.get("paid", False),
                "brand_organic_toggle": row.get("own_brand", False),
            },
            "source_info": {"source": "FILE_UPLOAD", "video_size": size, "chunk_size": chunk, "total_chunk_count": count},
        },
    )
    dest = upload_url(response["upload_url"], {"open-upload.tiktokapis.com", "open-upload-va.tiktokapis.com", "open-upload-sg.tiktokapis.com"})
    with media.open("rb") as file:
        for i in range(count):
            start = file.tell()
            content = file.read(size - start if i == count - 1 else chunk)
            call("PUT", dest, data=content, headers={"Content-Type": "video/mp4", "Content-Range": f"bytes {start}-{file.tell()-1}/{size}"})
    return response["publish_id"]


def metrics(platform, external):
    if platform == "youtube":
        items = call("GET", YT + "/videos", platform, params={"part": "statistics", "id": external}).json()["items"]
        if not items:
            raise ValueError("YouTube statistics are unavailable.")
        row = items[0]["statistics"]
        return {k: int(row[v]) for k, v in (("views", "viewCount"), ("likes", "likeCount"), ("comments", "commentCount")) if v in row}
    if platform == "x":
        row = call("GET", X + "/tweets/" + external, platform, params={"tweet.fields": "public_metrics"}).json()["data"]
        pm = row.get("public_metrics") or {}
        return {k: int(pm[v]) for k, v in (("views", "impression_count"), ("likes", "like_count"), ("comments", "reply_count"), ("shares", "retweet_count")) if v in pm}
    if platform == "instagram":
        rows = call("GET", IG + "/" + external + "/insights", platform, params={"metric": "views,likes,comments,shares"}).json()["data"]
        return {r["name"]: int(r["values"][0]["value"]) for r in rows if r.get("values")}
    if platform == "facebook":
        row = call("GET", FB + "/" + external, platform, params={"fields": "views,likes.summary(true),comments.summary(true)"}).json()
        out = {}
        if "views" in row:
            out["views"] = int(row["views"])
        if isinstance(row.get("likes"), dict) and "total_count" in (row["likes"].get("summary") or {}):
            out["likes"] = int(row["likes"]["summary"]["total_count"])
        if isinstance(row.get("comments"), dict) and "total_count" in (row["comments"].get("summary") or {}):
            out["comments"] = int(row["comments"]["summary"]["total_count"])
        return out
    if platform == "threads":
        rows = call("GET", TH + "/" + external + "/insights", platform, params={"metric": "views,likes,replies,reposts"}).json()["data"]
        out = {}
        for r in rows:
            vals = r.get("values") or []
            val = vals[0].get("value") if vals else (r.get("total_value") or {}).get("value")
            if val is not None:
                key = {"replies": "comments", "reposts": "shares"}.get(r["name"], r["name"])
                out[key] = int(val)
        return out
    if platform in ("linkedin", "custom"):
        raise ValueError("Analytics refresh is not available for this platform.")
    info = tt("/post/publish/status/fetch/", {"publish_id": external})
    ids = info.get("publicaly_available_post_id") or info.get("publicly_available_post_id")
    if not ids:
        raise ValueError("TikTok has no public post ID yet.")
    result = tt("/video/query/?fields=id,view_count,like_count,comment_count,share_count", {"filters": {"video_ids": [str(ids[0])]}})
    v = result["videos"][0]
    return {k: int(v[f]) for k, f in (("views", "view_count"), ("likes", "like_count"), ("comments", "comment_count"), ("shares", "share_count")) if f in v}


@contextmanager
def connect(data):
    db = sqlite3.connect(data / "jobs.sqlite3", timeout=15)
    db.row_factory = sqlite3.Row
    try:
        with db:
            yield db
    finally:
        db.close()


def _ensure_posts_table(data):
    with connect(data) as db:
        db.execute("CREATE TABLE IF NOT EXISTS posts(id TEXT PRIMARY KEY, payload TEXT, status TEXT, external TEXT, metrics TEXT, error TEXT)")


def pick_post_slot(earliest, previous, gap_minutes, daily_cap, tz_minutes):
    """Find the first permitted local-day slot without moving other queued posts."""
    gap = gap_minutes * 60
    offset = tz_minutes * 60
    candidate = earliest
    for past in sorted(previous):
        if gap and abs(candidate - past) < gap:
            candidate = past + gap
    while daily_cap:
        day = math.floor((candidate + offset) / 86400)
        if sum(math.floor((stamp + offset) / 86400) == day for stamp in previous) < daily_cap:
            break
        candidate = (day + 1) * 86400 - offset
        for past in sorted(previous):
            if gap and abs(candidate - past) < gap:
                candidate = past + gap
    return candidate


def _queue_post(db, identifier, row):
    now = time.time()
    records = db.execute(
        """SELECT p.payload,p.status,j.created,j.updated,j.not_before
           FROM posts p JOIN jobs j ON json_extract(j.payload,'$.post')=p.id
           WHERE p.id!=? AND j.kind='social' AND j.status!='canceled'
             AND p.status IN ('waiting','sending','check platform','submitted')""",
        (identifier,),
    )
    previous = []
    for record in records:
        other = json.loads(record["payload"])
        if (other["platform"], other["account"]) != (row["platform"], row["account"]):
            continue
        previous.append(record["updated"] if record["status"] == "submitted" else record["not_before"] or record["created"])
    when = pick_post_slot(max(float(row.get("when", 0)), now), previous, row.get("gap_minutes", 0), row.get("daily_cap", 0), row.get("offset_minutes", 0))
    db.execute("INSERT INTO jobs VALUES(?,?,?,?,?,?,?,?,?,?)", (uuid.uuid4().hex, "social", json.dumps({"post": identifier}), "queued", now, now, when, None, "{}", 0))
    return when


def create_post(data, body, probe, wake_queue=None, note_error=None):
    platform = body["platform"]
    if platform not in PLATFORMS:
        raise ValueError("Choose a supported platform.")
    acct = account(platform)
    if body.get("account") != acct["id"] or body.get("privacy") not in acct["privacy"]:
        raise ValueError("Review the destination account and visibility.")
    clip = body["clip"]
    path = media_path(data, clip)
    record = json.loads((data / (clip + ".json")).read_text(encoding="utf-8"))
    if record.get("result", {}).get("status") != "done":
        raise ValueError("Select a finished library export.")
    if platform == "tiktok" and probe(path)["duration"] > acct["max_duration"]:
        raise ValueError("Clip exceeds this account's TikTok duration limit.")
    title = str(body.get("title", "")).strip()
    max_title = PLATFORM_INFO[platform]["max_title"]
    if not title or len(title) > max_title:
        raise ValueError("Enter a title within the platform limit.")
    when = float(body.get("when", 0))
    if when and not time.time() < when < time.time() + 366 * 86400:
        raise ValueError("Choose a future time within one year.")
    minutes = int(body.get("gap_minutes", 0))
    cap = int(body.get("daily_cap", 0))
    offset = int(body.get("offset_minutes", 0))
    if not (0 <= minutes <= 1440 and 0 <= cap <= 24 and -720 <= offset <= 840):
        raise ValueError("Check the post interval and daily limit.")
    needs_url = PLATFORM_INFO[platform]["requires_media_url"]
    row = {
        "platform": platform,
        "account": acct["id"],
        "name": acct["name"],
        "clip": clip,
        "title": title,
        "when": when,
        "privacy": body["privacy"],
        "media_url": str(body.get("media_url", "")) if needs_url else "",
        "own_brand": bool(body.get("own_brand")),
        "paid": bool(body.get("paid")),
        "gap_minutes": minutes,
        "daily_cap": cap,
        "offset_minutes": offset,
    }
    if body.get("description"):
        row["description"] = str(body["description"])[:5000]
    if body.get("hashtags"):
        row["hashtags"] = [str(t).lstrip("#")[:40] for t in list(body["hashtags"])[:20] if str(t).strip()]
    if needs_url and not row["media_url"].startswith("https://"):
        raise ValueError("Enter the hosted HTTPS URL of the selected clip.")
    identifier = uuid.UUID(body["request_id"]).hex
    _ensure_posts_table(data)
    with connect(data) as db:
        db.execute("BEGIN IMMEDIATE")
        existing = db.execute("SELECT payload FROM posts WHERE id=?", (identifier,)).fetchone()
        if existing:
            if json.loads(existing[0]) != row:
                raise ValueError("Use a fresh post request.")
            return {"post": identifier, "duplicate": True}
        draft = body.get("draft") is True
        db.execute("INSERT INTO posts VALUES(?,?,?,NULL,NULL,?)", (identifier, json.dumps(row), "draft" if draft else "waiting", note_error if draft else None))
        scheduled = None
        if not draft:
            scheduled = _queue_post(db, identifier, row)
    if not draft and wake_queue is not None:
        wake_queue.set()
    return {"post": identifier, "scheduled_at": scheduled}


def _clip_caption(clip, platform, include_hashtags=True):
    title = str(clip.get("title") or "NeonClipping clip").strip()
    desc = str(clip.get("description") or "").strip()
    tags = [str(t).lstrip("#").strip() for t in (clip.get("hashtags") or []) if str(t).strip()]
    hash_line = " ".join("#" + t for t in tags[:10]) if include_hashtags and tags else ""
    max_len = PLATFORM_INFO[platform]["max_title"]
    if platform == "youtube":
        full_desc = "\n\n".join(p for p in (title, desc, hash_line) if p)
        return title[:max_len], full_desc[:5000], tags
    parts = [title]
    if hash_line and len(title) + len(hash_line) + 1 <= max_len:
        parts.append(hash_line)
    elif desc and len(title) + len(desc) + 2 <= max_len:
        parts.append(desc)
    return " ".join(parts)[:max_len], "\n\n".join(p for p in (title, desc, hash_line) if p)[:5000], tags


def _resolve_media_url(template, clip_id):
    base = str(template or "").strip()
    if not base:
        return ""
    if "{clip}" in base:
        return base.replace("{clip}", clip_id)
    return base.rstrip("/") + "/" + clip_id + ".mp4"


def auto_queue_clip(app, data, clip, source="make"):
    """Automatically queue or save drafts for a finished clip across enabled platforms."""
    results = []
    try:
        cfg = read_auto_upload(data)
        if not cfg.get("enabled") or source not in (cfg.get("sources") or []):
            return results
        score = clip.get("score")
        min_score = int(cfg.get("min_score") or 0)
        if min_score > 0 and (score is None or float(score) < min_score):
            return results
        clip_id = str(clip.get("file") or clip.get("id") or "").strip()
        if not clip_id:
            return results
        probe = getattr(app, "neon", {}).get("probe") if hasattr(app, "neon") else None
        if not callable(probe):
            probe = getattr(app, "social_probe", None) or (lambda p: {"duration": 30})
        wake_queue = getattr(getattr(app, "processing_queue", None), "wake", None)
        flags = clip.get("flags") or []
        flagged = bool(flags) and bool(cfg.get("skip_flagged", True))
        flag_note = ("Check before posting (words to avoid): " + ", ".join(map(str, flags))) if flagged else None

        for platform in cfg.get("platforms") or []:
            if platform not in PLATFORMS:
                continue
            try:
                acct = account(platform)
                choices = acct.get("privacy") or []
                if not choices:
                    raise ValueError("No visibility options returned by platform.")
                wanted = (cfg.get("platform_privacy") or {}).get(platform)
                preferred = PLATFORM_INFO[platform]["default_privacy"]
                if wanted in choices:
                    privacy = wanted
                elif preferred in choices:
                    privacy = preferred
                else:
                    privacy = choices[0]
                title, description, hashtags = _clip_caption(clip, platform, cfg.get("include_hashtags", True))
                media_url = ""
                if PLATFORM_INFO[platform]["requires_media_url"]:
                    media_url = _resolve_media_url(cfg.get("media_base_url"), clip_id)
                    if not media_url.startswith("https://"):
                        raise ValueError("Hosted HTTPS URL is required for " + PLATFORM_INFO[platform]["label"] + ".")
                req_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"neonclipping:auto:{clip_id}:{platform}"))
                body = {
                    "platform": platform,
                    "account": acct["id"],
                    "privacy": privacy,
                    "clip": clip_id,
                    "title": title,
                    "description": description,
                    "hashtags": hashtags,
                    "media_url": media_url,
                    "when": 0,
                    "draft": bool(cfg.get("draft_only") or flagged),
                    "gap_minutes": int(cfg.get("gap_minutes") or 0),
                    "daily_cap": int(cfg.get("daily_cap") or 0),
                    "offset_minutes": int(cfg.get("offset_minutes") or 0),
                    "request_id": req_id,
                }
                created = create_post(data, body, probe, wake_queue=wake_queue, note_error=flag_note)
                results.append({"platform": platform, "status": "draft" if body["draft"] else "queued", **created})
            except Exception as error:
                results.append({"platform": platform, "status": "skipped", "error": str(error)})
    except Exception:
        pass
    return results


def platform_catalog(data=None):
    rows = []
    for pid in PLATFORMS:
        info = PLATFORM_INFO[pid]
        if pid == "custom":
            try:
                url, _ = _custom_endpoint(data)
                configured = bool(url)
            except ValueError:
                configured = False
        else:
            configured = bool(os.getenv("NEONCLIPPING_" + pid.upper() + "_TOKEN"))
            if not configured and pid in PROVIDERS:
                try:
                    from social_accounts import vault
                    configured = bool(vault(pid).get("access_token"))
                except ValueError:
                    configured = False
        rows.append({"id": pid, **info, "configured": configured})
    return rows


def attach(app, data, state, probe):
    _ctx["data"] = data
    app.social_probe = probe
    _ensure_posts_table(data)

    def run(body):
        job = uuid.uuid4().hex
        state[job] = {"status": "running", "stage": "Sending to platform"}

        def worker():
            sending = False
            try:
                with connect(data) as db:
                    changed = db.execute("UPDATE posts SET status='sending' WHERE id=? AND status='waiting'", (body["post"],)).rowcount
                    if not changed:
                        raise ValueError("This post was already attempted. Check its platform status.")
                    row = json.loads(db.execute("SELECT payload FROM posts WHERE id=?", (body["post"],)).fetchone()[0])
                media_path(data, row["clip"])
                current = account(row["platform"])
                if current["id"] != row["account"] or row["privacy"] not in current["privacy"]:
                    raise ValueError("The publishing account or visibility changed. Check the destination.")
                sending = True
                external = publish(row, data)
                with connect(data) as db:
                    db.execute("UPDATE posts SET status='submitted',external=? WHERE id=?", (external, body["post"]))
                state[job] = {"status": "done", "stage": "Submitted to " + row["platform"]}
            except Exception as e:
                error = str(e) if isinstance(e, ValueError) else "Posting failed. Check the platform account."
                stage = "check platform" if sending else "retryable"
                with connect(data) as db:
                    db.execute("UPDATE posts SET status=?,error=? WHERE id=? AND status='sending'", (stage, error, body.get("post", "")))
                state[job] = {"status": "error", "error": error}

        threading.Thread(target=worker, daemon=True).start()
        return {"job": job}

    @app.get("/social/platforms")
    def platforms():
        return {"platforms": platform_catalog(data)}

    @app.get("/social/auto")
    def get_auto():
        return {**public_auto_upload(data), "platforms_info": platform_catalog(data)}

    @app.post("/social/auto")
    def set_auto(body: dict):
        try:
            return {**save_auto_upload(data, body), "platforms_info": platform_catalog(data)}
        except (ValueError, TypeError) as error:
            raise HTTPException(400, str(error)) from error

    @app.get("/social/account/{platform}")
    def destination(platform: str):
        try:
            return account(platform)
        except (ValueError, KeyError, IndexError) as error:
            raise HTTPException(400, str(error)) from error

    @app.get("/social/posts")
    def posts():
        with connect(data) as db:
            jobs = {
                json.loads(j["payload"]).get("post"): dict(j)
                for j in db.execute("SELECT id,status,payload,created,updated,not_before FROM jobs WHERE kind='social' ORDER BY created")
            }
            return [
                {
                    "id": r["id"],
                    "job": jobs.get(r["id"], {}).get("id"),
                    "status": jobs.get(r["id"], {}).get("status", "waiting") if r["status"] == "waiting" else r["status"],
                    "external": r["external"],
                    "metrics": json.loads(r["metrics"] or "{}"),
                    "error": r["error"],
                    "scheduled_at": jobs.get(r["id"], {}).get("not_before"),
                    "submitted_at": jobs.get(r["id"], {}).get("updated") if r["status"] == "submitted" else None,
                    **json.loads(r["payload"]),
                }
                for r in db.execute("SELECT * FROM posts ORDER BY rowid DESC LIMIT 100")
            ]

    @app.post("/social/posts")
    def submit(body: dict):
        try:
            wake = getattr(getattr(app, "processing_queue", None), "wake", None)
            created = create_post(data, body, probe, wake_queue=wake)
            return {"post": created["post"]}
        except (OSError, KeyError, ValueError, TypeError, OverflowError) as error:
            raise HTTPException(400, str(error)) from error

    @app.post("/social/posts/batch")
    def submit_batch(body: dict):
        platforms_list = body.get("platforms") or []
        if not isinstance(platforms_list, list) or not platforms_list:
            raise HTTPException(400, "Choose at least one platform.")
        clip = str(body.get("clip") or "")
        title = str(body.get("title") or "").strip()
        if not clip or not title:
            raise HTTPException(400, "Choose a clip and enter a title.")
        wake = getattr(getattr(app, "processing_queue", None), "wake", None)
        results = []
        base_req = str(body.get("request_id") or uuid.uuid4())
        for platform in platforms_list:
            p = str(platform or "").strip().lower()
            try:
                if p not in PLATFORMS:
                    raise ValueError(f"Unsupported platform: {p}.")
                acct = account(p)
                choices = acct.get("privacy") or []
                wanted_map = body.get("platform_privacy") or {}
                privacy = wanted_map.get(p) if isinstance(wanted_map, dict) and wanted_map.get(p) in choices else None
                if not privacy:
                    default_p = PLATFORM_INFO[p]["default_privacy"]
                    privacy = default_p if default_p in choices else (choices[0] if choices else "")
                req_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"batch:{base_req}:{p}"))
                item = {
                    "platform": p,
                    "account": acct["id"],
                    "privacy": privacy,
                    "clip": clip,
                    "title": title[: PLATFORM_INFO[p]["max_title"]],
                    "media_url": str(body.get("media_url") or ""),
                    "when": float(body.get("when") or 0),
                    "own_brand": bool(body.get("own_brand")),
                    "paid": bool(body.get("paid")),
                    "draft": bool(body.get("draft")),
                    "gap_minutes": int(body.get("gap_minutes") or 0),
                    "daily_cap": int(body.get("daily_cap") or 0),
                    "offset_minutes": int(body.get("offset_minutes") or 0),
                    "request_id": req_id,
                }
                created = create_post(data, item, probe, wake_queue=wake)
                results.append({"platform": p, "ok": True, **created})
            except (OSError, KeyError, ValueError, TypeError, OverflowError) as error:
                results.append({"platform": p, "ok": False, "error": str(error)})
        if not any(r["ok"] for r in results):
            raise HTTPException(400, "; ".join(f"{r['platform']}: {r['error']}" for r in results))
        return {"results": results}

    @app.post("/social/posts/{post}/approve")
    def approve(post: str):
        with connect(data) as db:
            db.execute("BEGIN IMMEDIATE")
            draft = db.execute("SELECT payload,status FROM posts WHERE id=?", (post,)).fetchone()
            if not draft or draft["status"] not in ("draft", "retryable"):
                raise HTTPException(409, "This draft is no longer awaiting approval.")
            row = json.loads(draft["payload"])
            when = _queue_post(db, post, row)
            db.execute("UPDATE posts SET status='waiting',error=NULL WHERE id=?", (post,))
        app.processing_queue.wake.set()
        return {"scheduled_at": when}

    @app.post("/social/posts/{post}/metrics")
    def refresh(post: str):
        with connect(data) as db:
            row = db.execute("SELECT * FROM posts WHERE id=?", (post,)).fetchone()
            if not row or not row["external"]:
                raise HTTPException(409, "No submitted post yet.")
            try:
                settings = json.loads(row["payload"])
                result = metrics(settings["platform"], row["external"])
            except (ValueError, KeyError, IndexError) as error:
                raise HTTPException(400, str(error)) from error
            db.execute("UPDATE posts SET metrics=? WHERE id=?", (json.dumps(result), post))
        return result

    return run


def duration_preferences(data):
    """Small platform-relative tie breaker after at least six measured posts on a platform."""
    if not (data / "jobs.sqlite3").exists():
        return {}
    by_platform = {}
    with connect(data) as db:
        for row in db.execute("SELECT payload,metrics FROM posts WHERE metrics IS NOT NULL"):
            settings = json.loads(row["payload"])
            m = json.loads(row["metrics"])
            if m.get("views", 0) < 100:
                continue
            try:
                record = json.loads((data / (settings["clip"] + ".json")).read_text(encoding="utf-8"))
                bucket = int(record["result"]["meta"]["duration"] // 15)
            except (OSError, KeyError, ValueError):
                continue
            by_platform.setdefault((settings["platform"], settings["account"]), []).append(
                (bucket, (m.get("likes", 0) + m.get("comments", 0)) / m["views"])
            )
    scores = {}
    for rows in by_platform.values():
        if len(rows) < 6:
            continue
        baseline = sum(rate for _, rate in rows) / len(rows)
        if baseline <= 0:
            continue
        for bucket, rate in rows:
            scores.setdefault(bucket, []).append(rate / baseline - 1)
    return {k: max(-0.03, min(0.03, 0.03 * sum(v) / len(v))) for k, v in scores.items() if len(v) >= 2}

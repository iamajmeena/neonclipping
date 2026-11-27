"""Local account authorization via the platform's own consent screen."""
import base64
import hashlib
import json
import logging
import os
import secrets
import threading
import time
from urllib.parse import parse_qs, urlencode, urlparse

from fastapi import HTTPException
from fastapi.responses import JSONResponse
import requests

PROVIDERS={
    "youtube":("https://accounts.google.com/o/oauth2/v2/auth","https://oauth2.googleapis.com/token",
               "https://www.googleapis.com/auth/youtube.upload https://www.googleapis.com/auth/youtube.readonly"),
    "x":("https://twitter.com/i/oauth2/authorize","https://api.x.com/2/oauth2/token",
         "tweet.read tweet.write users.read media.write offline.access"),
    "instagram":("https://www.instagram.com/oauth/authorize","https://api.instagram.com/oauth/access_token",
                 "instagram_business_basic,instagram_business_content_publish,instagram_business_manage_insights"),
    "facebook":("https://www.facebook.com/v21.0/dialog/oauth","https://graph.facebook.com/v21.0/oauth/access_token",
                "pages_show_list,pages_read_engagement,pages_manage_posts,publish_video"),
    "tiktok":("https://www.tiktok.com/v2/auth/authorize/","https://open.tiktokapis.com/v2/oauth/token/",
              "user.info.basic,video.publish,video.list"),
    "linkedin":("https://www.linkedin.com/oauth/v2/authorization","https://www.linkedin.com/oauth/v2/accessToken",
                "openid profile w_member_social"),
    "threads":("https://threads.net/oauth/authorize","https://graph.threads.net/oauth/access_token",
               "threads_basic,threads_content_publish,threads_manage_insights"),
}
PKCE_PLATFORMS={"youtube","x","tiktok"}
pending={}
lock=threading.RLock()


def config(platform):
    if platform not in PROVIDERS:raise ValueError("Unknown platform.")
    prefix="NEONCLIPPING_"+platform.upper()+"_"
    client=os.getenv(prefix+"CLIENT_ID")
    redirect=os.getenv(prefix+"REDIRECT_URI","http://127.0.0.1:"+os.getenv("NEONCLIPPING_PORT","8770")+"/social-callback")
    if not client:raise ValueError("Set "+prefix+"CLIENT_ID for your developer app.")
    uri=urlparse(redirect)
    if uri.scheme!="https" and not (uri.scheme=="http" and uri.hostname in ("127.0.0.1","localhost")):
        raise ValueError("Register an HTTPS or loopback callback URL.")
    return client,os.getenv(prefix+"CLIENT_SECRET",""),redirect


def vault(platform,value=None):
    try:
        import keyring
        if value is None:return json.loads(keyring.get_password("NeonClipping Social",platform) or "{}")
        keyring.set_password("NeonClipping Social",platform,json.dumps(value))
    except Exception:
        raise ValueError("Install keyring and unlock the OS credential store, or configure a platform token in the environment.") from None


def begin(platform):
    if platform=="custom":
        raise ValueError("Custom upload endpoints use a webhook URL and optional token instead of OAuth.")
    client,_,redirect=config(platform)
    if os.getenv("NEONCLIPPING_"+platform.upper()+"_TOKEN"):
        raise ValueError("An environment token supplies this account. Remove it before connecting a different account.")
    vault(platform)
    state=secrets.token_urlsafe(32)
    verifier=secrets.token_urlsafe(60)
    with lock:
        for old,entry in list(pending.items()):
            if entry[0]<time.monotonic():pending.pop(old,None)
        pending[state]=(time.monotonic()+600,platform,verifier,redirect)
    args={"client_key" if platform=="tiktok" else "client_id":client,"redirect_uri":redirect,"scope":PROVIDERS[platform][2],
          "response_type":"code","state":state}
    if platform in PKCE_PLATFORMS:
        digest=hashlib.sha256(verifier.encode()).digest()
        args.update(code_challenge=base64.urlsafe_b64encode(digest).decode().rstrip("="),code_challenge_method="S256")
    if platform=="youtube":args.update(access_type="offline",prompt="consent")
    return {"url":PROVIDERS[platform][0]+"?"+urlencode(args)}


def exchange(url,fields,method="POST",**extra):
    try:
        opts={"params":fields} if method=="GET" else {"data":fields}
        if extra.get("auth"):opts["auth"]=extra["auth"]
        if extra.get("headers"):opts["headers"]=extra["headers"]
        response=requests.request(method,url,timeout=30,allow_redirects=False,**opts)
        if not response.ok:raise ValueError("The platform declined authorization. Check the redirect URI, app settings and account permissions.")
        result=response.json()
    except requests.RequestException:
        raise ValueError("The token service could not be reached.") from None
    if not result.get("access_token"):raise ValueError("The platform did not return an access token.")
    result["expires_at"]=time.time()+float(result.get("expires_in",3600))
    return result


def finish(raw):
    uri=urlparse(raw)
    fields=parse_qs(uri.query)
    with lock:entry=pending.pop((fields.get("state") or [""])[0],None)
    if not entry or entry[0]<time.monotonic():raise ValueError("Authorization expired. Start Connect again.")
    _,platform,verifier,redirect=entry
    registered=urlparse(redirect)
    if (uri.scheme,uri.netloc,uri.path)!=(registered.scheme,registered.netloc,registered.path):
        raise ValueError("The callback URL differs from the registered redirect.")
    code=(fields.get("code") or [""])[0]
    if not code:raise ValueError("Authorization was canceled.")
    client,secret,_=config(platform)
    payload={"client_key" if platform=="tiktok" else "client_id":client,"code":code,
             "redirect_uri":redirect,"grant_type":"authorization_code"}
    extra={}
    if platform=="x" and secret:
        extra["auth"]=(client,secret)
    elif secret:
        payload["client_secret"]=secret
    if platform in PKCE_PLATFORMS:payload["code_verifier"]=verifier
    result=exchange(PROVIDERS[platform][1],payload,**extra)
    if platform=="instagram":
        result=exchange("https://graph.instagram.com/access_token",{"grant_type":"ig_exchange_token","client_secret":secret,
                        "access_token":result["access_token"]},"GET")
    elif platform=="facebook" and secret:
        result=exchange("https://graph.facebook.com/v21.0/oauth/access_token",{"grant_type":"fb_exchange_token","client_id":client,
                        "client_secret":secret,"fb_exchange_token":result["access_token"]},"GET")
    elif platform=="threads" and secret:
        result=exchange("https://graph.threads.net/access_token",{"grant_type":"th_exchange_token","client_secret":secret,
                        "access_token":result["access_token"]},"GET")
    vault(platform,result)
    return {"platform":platform}


def access_token(platform):
    if platform not in PROVIDERS:raise ValueError("Unknown platform.")
    env=os.getenv("NEONCLIPPING_"+platform.upper()+"_TOKEN")
    if env:return env
    with lock:
        record=vault(platform)
        if not record.get("access_token"):raise ValueError("Connect your account first.")
        margin=86400 if platform in ("instagram","threads") else 120
        if record.get("expires_at",0)>time.time()+margin:return record["access_token"]
        if platform=="instagram":
            result=exchange("https://graph.instagram.com/refresh_access_token",{"grant_type":"ig_refresh_token","access_token":record["access_token"]},"GET")
        elif platform=="threads":
            result=exchange("https://graph.threads.net/refresh_access_token",{"grant_type":"th_refresh_token","access_token":record["access_token"]},"GET")
        else:
            client,secret,_=config(platform)
            if not record.get("refresh_token"):raise ValueError("Reconnect this account to renew access.")
            payload={"client_key" if platform=="tiktok" else "client_id":client,"refresh_token":record["refresh_token"],"grant_type":"refresh_token"}
            extra={}
            if platform=="x" and secret:
                extra["auth"]=(client,secret)
            elif secret:
                payload["client_secret"]=secret
            result=exchange(PROVIDERS[platform][1],payload,**extra)
        vault(platform,{**record,**result})
        return result["access_token"]


def attach(app):
    from fastapi.responses import HTMLResponse
    class RedactCallback(logging.Filter):
        def filter(self,record):
            args=record.args
            if isinstance(args,tuple) and len(args)==5 and str(args[2]).startswith("/social-callback?"):
                record.args=(*args[:2],"/social-callback",*args[3:])
            return True
    logging.getLogger("uvicorn.access").addFilter(RedactCallback())
    @app.middleware("http")
    async def local_social(request,call_next):
        if request.url.path.startswith("/social/") or request.url.path=="/social-callback":
            origin=request.headers.get("origin")
            sec_site=request.headers.get("sec-fetch-site")
            if (origin and origin!=str(request.base_url).rstrip("/")) or sec_site=="cross-site":
                return JSONResponse({"detail":"Open publishing from the NeonClipping app."},status_code=403)
        return await call_next(request)

    @app.post("/social/connect/{platform}")
    def connect(platform:str):
        try:return begin(platform)
        except ValueError as error:raise HTTPException(400,str(error)) from error

    @app.post("/social/authorize")
    def authorize(body:dict):
        try:return finish(str(body.get("redirect","")))
        except ValueError as error:raise HTTPException(400,str(error)) from error

    @app.post("/social/disconnect/{platform}")
    def disconnect(platform:str):
        if platform=="custom":
            return {"ok":True}
        if platform not in PROVIDERS:raise HTTPException(400,"Unknown platform.")
        try:vault(platform,{})
        except ValueError as error:raise HTTPException(400,str(error)) from error
        return {"ok":True}

    @app.get("/social-callback")
    def callback():
        return HTMLResponse("""<!doctype html><meta name="referrer" content="no-referrer"><title>NeonClipping account</title>
        <p id="message">Connecting your account…</p><script>
        const redirect=location.href;history.replaceState(null,'',location.pathname);
        fetch('/social/authorize',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({redirect})})
        .then(async r=>{const v=await r.json();document.getElementById('message').textContent=r.ok?'Account connected. Return to NeonClipping and check the account.':v.detail;})
        .catch(()=>document.getElementById('message').textContent='The local app could not finish authorization.');
        </script>""",headers={"Cache-Control":"no-store","Referrer-Policy":"no-referrer"})

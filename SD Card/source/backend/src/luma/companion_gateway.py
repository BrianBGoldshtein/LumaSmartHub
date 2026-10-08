"""Fixed private remote API ingress; no dashboard/API pass-through or cookies."""
from __future__ import annotations

import asyncio
import base64
from collections import deque
import ipaddress
import json
import os
from pathlib import Path
import re
from time import monotonic

import httpx
from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse, FileResponse, RedirectResponse

from .companion_auth import OPERATIONS, TOKEN, _identity_digest, private_origin
from .companion_api import parse_object

HUB = "http://127.0.0.1:8742/api/v1/companion/"
CSP = ("default-src 'none'; script-src 'self'; style-src 'self'; style-src-attr 'unsafe-inline'; "
       "font-src 'self'; img-src 'self' data:; connect-src 'self'; base-uri 'none'; "
       "frame-ancestors 'none'; form-action 'self'")


def _single(request: Request, name: str, *, required=True):
    values = request.headers.getlist(name)
    if len(values) > 1 or (required and len(values) != 1):
        raise HTTPException(403, "Private Luma connection required.")
    return values[0] if values else None


def connection_context(request: Request, *, callback=False):
    # In production this listener is bound to loopback and firewalled. Serve
    # overwrites identity/forwarded headers; local processes are trusted hosts.
    try:
        if not ipaddress.ip_address(request.client.host).is_loopback: raise ValueError
        if _single(request,"Tailscale-Funnel-Request",required=False) is not None: raise ValueError
        host = _single(request,"Host")
        if _single(request,"X-Forwarded-Proto") != "https": raise ValueError
        origin = private_origin("https://" + host)
        identity = _single(request,"Tailscale-User-Login")
        _identity_digest(identity)
        supplied = _single(request,"Origin",required=False)
        if supplied is not None and supplied != origin: raise ValueError
        if request.method not in {"GET", "HEAD"} and supplied != origin: raise ValueError
        if request.url.query and not callback: raise ValueError
        return origin, identity
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(403, "Private Luma connection required.") from None


async def request_body(request, *, limit=65536):
    if _single(request,"Content-Encoding",required=False):
        raise HTTPException(415,"Use an uncompressed JSON request.")
    if request.method == "GET":
        limit = 0
    elif _single(request,"Content-Type") != "application/json":
        raise HTTPException(415,"Use a JSON request.")
    raw = bytearray()
    async for chunk in request.stream():
        if len(raw) + len(chunk) > limit:
            raise HTTPException(413,"Remote request is too large.")
        raw.extend(chunk)
    return bytes(raw)


def install_companion_gateway(app, transport=None, *, frontend_dir=None):
    calls: deque[float] = deque()
    asset_calls: deque[float] = deque()
    # A separate production build contains only remote UI and bundled fonts.
    # Do not serve the wall entry, its animation code, source maps or API paths.
    root=(Path(frontend_dir or os.environ.get('LUMA_FRONTEND_DIR','/opt/luma/frontend'))/'assets').resolve()

    def budget(*,static=False):
        now = monotonic()
        entries=asset_calls if static else calls
        while entries and now - entries[0] >= 60: entries.popleft()
        # Every authorized read requires a challenge plus the signed request.
        # Opening Settings/Calendars loads preview, settings and three catalog
        # resources; allow that bounded burst without increasing minute budget.
        if len(entries) >= (120 if static else 180) or sum(now - instant < 1 for instant in entries) >= 24:
            raise HTTPException(429,"Remote is busy. Try again shortly.",headers={"Retry-After":"5"})
        entries.append(now)

    async def send(action: str, payload):
        # action is a controller-selected constant, never a request field.
        try:
            async with asyncio.timeout(48):
                async with httpx.AsyncClient(transport=transport,trust_env=False,follow_redirects=False,timeout=46) as client:
                    async with client.stream("POST",HUB+action,json=payload,
                            headers={"Accept-Encoding":"identity"}) as response:
                        if response.headers.get("content-encoding") or response.headers.get("content-type"," ").split(';')[0]!='application/json':
                            raise ValueError
                        raw = bytearray()
                        async for chunk in response.aiter_bytes():
                            if len(raw)+len(chunk)>1024*1024: raise ValueError
                            raw.extend(chunk)
                        value = json.loads(raw)
                        status = response.status_code
            if status not in {200,202,403,409,410,413,415,422,429,501,503}:
                raise ValueError
            if status >= 400:
                # Do not blindly forward an unexpected local provider/error.
                message = {403:"Connect the selected iPhone and check browser enrollment.",
                    409:"Hub state changed. Refresh before trying again.",
                    410:"This review expired. Check again.",
                    501:"This remote feature is still being prepared."}.get(status,
                    "Hub operation unavailable. Refresh before trying again.")
                value = {"detail":message}
            return JSONResponse(value,status_code=status,headers={"Cache-Control":"no-store"})
        except (httpx.HTTPError,TimeoutError,ValueError,RecursionError):
            raise HTTPException(503,"Luma is restarting or unavailable. Reconnect and refresh.") from None

    @app.get('/remote')
    async def entry_redirect(request: Request):
        connection_context(request);budget(static=True)
        return RedirectResponse('/remote/',status_code=307,headers={'Cache-Control':'no-store'})

    @app.get('/remote/')
    async def entry(request: Request):
        connection_context(request);budget(static=True)
        file=root/'remote-index.html'
        if file.is_symlink() or not file.is_file() or file.stat().st_size>2*1024*1024:
            raise HTTPException(503,'Remote interface unavailable. Check the installed release.')
        return FileResponse(file,media_type='text/html')

    async def asset(request: Request,asset_path: str):
        connection_context(request);budget(static=True)
        if asset_path not in {'manifest.webmanifest','icon.svg','touch-icon.png','icon-192.png','icon-512.png'} and not re.fullmatch(
                r'assets/remote-[A-Za-z0-9_-]+\.(js|css|woff2?|svg|png)',asset_path):
            raise HTTPException(404,'Remote asset unavailable.')
        name=asset_path.removeprefix('assets/') if asset_path.startswith('assets/') else 'remote-'+asset_path
        file=root/name
        if file.is_symlink():raise HTTPException(404,'Remote asset unavailable.')
        candidate=file.resolve()
        if root not in candidate.parents or not candidate.is_file() or candidate.stat().st_size>2*1024*1024:
            raise HTTPException(404,'Remote asset unavailable.')
        return FileResponse(candidate,media_type='application/manifest+json' if asset_path=='manifest.webmanifest' else None)

    @app.get('/remote/google/callback')
    async def google_callback(request: Request):
        origin,identity=connection_context(request,callback=True);budget()
        if len(request.url.query)>8192:raise HTTPException(413,'Sign-in callback is too large.')
        result=await send('google-callback',{'origin':origin,'identity':identity,'query':request.url.query})
        try:connected=json.loads(result.body).get('connected') is True and result.status_code==200
        except (ValueError,TypeError):connected=False
        # Strip code/state from history; no arbitrary redirect or callback data.
        return RedirectResponse('/remote/#google='+('ok' if connected else 'failed'),status_code=303)

    @app.get("/remote/api/bootstrap")
    async def bootstrap(request: Request):
        origin,identity=connection_context(request);budget()
        await request_body(request)
        return await send("protocol",{"action":"bootstrap","origin":origin,"identity":identity})

    @app.post("/remote/api/enroll")
    async def enroll(request: Request):
        origin,identity=connection_context(request);budget()
        value=parse_object(await request_body(request,limit=2048))
        if set(value)!={"ticket","public_key","signature"}:
            raise HTTPException(422,"Enrollment request is invalid.")
        return await send("protocol",{**value,"action":"claim","origin":origin,"identity":identity})

    @app.post("/remote/api/challenge")
    async def challenge(request: Request):
        origin,identity=connection_context(request);budget()
        value=parse_object(await request_body(request,limit=2048))
        if set(value)!={"device_id","method","path","body_digest"}:
            raise HTTPException(422,"Remote request is invalid.")
        return await send("protocol",{**value,"action":"challenge","origin":origin,"identity":identity})

    async def signed(request: Request):
        origin,identity=connection_context(request);budget()
        device=_single(request,"X-Luma-Device")
        nonce=_single(request,"X-Luma-Nonce")
        signature=_single(request,"X-Luma-Proof")
        if not TOKEN.fullmatch(device) or not TOKEN.fullmatch(nonce) or not isinstance(signature,str) or len(signature)!=86:
            raise HTTPException(403,"Remote proof required.")
        raw=await request_body(request)
        return await send("dispatch",{"origin":origin,"identity":identity,"device_id":device,"nonce":nonce,
            "signature":signature,"method":request.method,"path":request.url.path,"body":base64.b64encode(raw).decode()})

    for method,path in sorted(OPERATIONS):
        app.add_api_route(path,signed,methods=[method])

    # The catchall follows fixed API routes; assets cannot shadow signed reads.
    app.add_api_route('/remote/{asset_path:path}',asset,methods=['GET'])

    @app.middleware("http")
    async def headers(request,call_next):
        response=await call_next(request)
        if request.url.path=='/remote' or request.url.path.startswith("/remote/"):
            response.headers.update({"Cache-Control":"no-store","Referrer-Policy":"no-referrer",
                "X-Content-Type-Options":"nosniff",
                "X-Frame-Options":"DENY","Content-Security-Policy":CSP,
                "Permissions-Policy":"camera=(), microphone=(), geolocation=()"})
        return response

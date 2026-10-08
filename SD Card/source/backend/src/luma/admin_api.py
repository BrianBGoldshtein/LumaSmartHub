"""Local primary-PIN cookie and an administration gate for existing APIs."""
from __future__ import annotations

from fastapi import Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from .admin_authority import AdminAuthority, AdminDenied, COOKIE, FRESH_PATHS, LEASE_SECONDS, COMMAND_PATHS, needs_admin


class AdminPin(BaseModel):
    model_config = ConfigDict(extra='forbid')
    pin: str = Field(min_length=4, max_length=8, pattern=r'^[0-9]+$')


def request_origin(request):
    return f'{request.url.scheme}://{request.url.netloc}'


def set_admin_cookie(response, token, request):
    response.set_cookie(COOKIE, token, max_age=LEASE_SECONDS, httponly=True,
                        secure=request.url.scheme == 'https', samesite='strict', path='/api/v1')


def install_admin_api(app, service, security, local_only, decode_command):
    admin = app.state.admin = AdminAuthority(service.storage)

    def bootstrap():
        return (not security.pin_is_configured() and not service.settings.onboarding_completed
                and len(service.profiles.list()) == 1)

    @app.get('/api/v1/admin/status', dependencies=[Depends(local_only)])
    def status(request: Request):
        try:
            remaining = admin.require_local(request.cookies.get(COOKIE), request_origin(request))
        except AdminDenied:
            remaining = 0
        return JSONResponse({'configured': security.pin_is_configured(), 'unlocked': remaining > 0,
                             'expires_in_seconds': remaining, 'bootstrap': bootstrap()},
                            headers={'Cache-Control': 'no-store'})

    @app.post('/api/v1/admin/unlock', dependencies=[Depends(local_only)])
    def unlock(payload: AdminPin, request: Request):
        try:
            token = admin.unlock_local(payload.pin, request_origin(request), previous=request.cookies.get(COOKIE))
        except AdminDenied:
            raise HTTPException(403, 'Incorrect primary PIN, or too many attempts. After five failures, wait one minute.') from None
        response = JSONResponse({'unlocked': True, 'expires_in_seconds': LEASE_SECONDS}, headers={'Cache-Control':'no-store'})
        set_admin_cookie(response, token, request)
        return response

    @app.post('/api/v1/admin/lock', dependencies=[Depends(local_only)])
    def lock(request: Request):
        admin.lock_local(request.cookies.get(COOKIE))
        response = JSONResponse({'unlocked': False}, headers={'Cache-Control':'no-store'})
        response.delete_cookie(COOKIE, path='/api/v1')
        return response

    @app.middleware('http')
    async def primary_gate(request: Request, call_next):
        path, method = request.url.path, request.method
        command = None
        if path in COMMAND_PATHS and method == 'POST':
            try:
                body = await request.json()
                if isinstance(body, dict):
                    command = decode_command(path, body)
            except (ValueError, TypeError):
                pass  # The existing controller still validates malformed input.
        if not needs_admin(method, path, command):
            return await call_next(request)
        try:
            local_only(request)  # A LAN token is not primary administration; signed remotes use the guarded loopback dispatch.
            # First local provisioning is the sole exception. Updates always
            # require a primary PIN, and adding a guest ends bootstrap access.
            if not security.pin_is_configured() and path == '/api/v1/security/pin':
                return await call_next(request)
            if bootstrap() and not path.startswith('/api/v1/updates/'):
                return await call_next(request)
            check = request.scope.get('luma_admin_check')
            if check is None:
                token, origin = request.cookies.get(COOKIE), request_origin(request)
                def check():
                    admin.require_local(token, origin, fresh=path in FRESH_PATHS or method == 'DELETE')
                request.scope['luma_admin_check'] = check
            check()
            response = await call_next(request)
            if method in {'GET', 'HEAD'}:
                check()  # Do not return a slow private read after lease expiry.
            return response
        except AdminDenied as error:
            return JSONResponse({'detail':str(error), 'code':'admin_required', 'fresh':error.fresh},
                                status_code=403, headers={'Cache-Control':'no-store'})
        except HTTPException as error:
            return JSONResponse({'detail':error.detail}, status_code=error.status_code, headers=error.headers)

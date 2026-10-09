"""Primary user management and a fixed, delegated own-account wall API."""
from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

from fastapi import Depends, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel, ConfigDict, Field

from .admin_api import request_origin
from .companion_api import _body, remote_guard
from .companion_profiles import own_operation
from .profiles import PRIMARY_ID, ProfileError, SETUP_STAGES
from .user_setup import COOKIE, BOUND_SECONDS, UserSetup, SetupDenied, wall_cookie
from .user_setup_google import UserSetupGoogle
from .companion_auth import CompanionDenied, private_origin
from .tailscale_setup import tailscale_request
from .pi_connect_setup import qr_data

class Management(BaseModel):
    model_config = ConfigDict(extra='forbid')
    action: str
    profile_id: str | None = None
    nickname: str | None = Field(default=None, max_length=24)


class Progress(BaseModel):
    model_config = ConfigDict(extra='forbid')
    stage: str
    wall_share_approved: bool | None = None


def install_user_setup_api(app, service, local_only):
    setup = app.state.user_setup = UserSetup(app)
    setup.desktop = UserSetupGoogle(setup)
    from .user_wall_api import install_user_wall_api
    install_user_wall_api(app, service, setup, local_only)

    @app.exception_handler(SetupDenied)
    async def setup_denied(request, error):
        return JSONResponse({'detail':str(error), 'code':'personal_setup_required'}, status_code=403,
                            headers={'Cache-Control':'no-store'})

    def response(value):
        return JSONResponse(value, headers={'Cache-Control':'no-store'})

    def current(request, *, draft=False):
        return setup.recheck(request.cookies.get(COOKIE), request_origin(request), allow_draft=draft)

    @app.get('/api/v1/users', dependencies=[Depends(local_only)])
    async def users(request: Request):
        remote_guard(request)
        return response({'users':[{'profile_id':user.id, 'role':user.role, 'nickname':user.nickname,
            'phone_registered':bool(user.phone_address), 'setup_stage':user.setup_stage,
            'wall_share_approved':user.wall_share_approved,
            'connected':app.state.bluetooth.companion_presence(user.id).authorized}
            for user in setup.profiles.list()], 'capacity':5})

    @app.post('/api/v1/users/manage', dependencies=[Depends(local_only)])
    async def manage(payload: Management, request: Request):
        if not app.state.security.pin_is_configured():
            raise HTTPException(409, 'Set the primary PIN before adding or managing users.')
        remote_guard(request)  # Check again immediately before the mutation.
        try:
            with setup.lock, app.state.companion.lock:
                if payload.action in {'create','resume','clear_phone'} and setup.pairing_active():
                    raise ProfileError('Finish or cancel the personal pairing before opening another setup.')
                if payload.action == 'create':
                    if payload.profile_id is not None or payload.nickname is None:
                        raise ProfileError('Name the new user.')
                    user = setup.profiles.create_secondary(payload.nickname)
                else:
                    if payload.profile_id is None:
                        raise ProfileError('Choose a user.')
                    user = setup.profiles.get(payload.profile_id)
                    if payload.action == 'rename':
                        if payload.nickname is None:
                            raise ProfileError('Name the user.')
                        user = setup.profiles.rename(user.id, payload.nickname)
                    elif payload.action == 'resume':
                        if payload.nickname is not None:
                            raise ProfileError('Choose a user without changing their name.')
                    elif payload.action == 'clear_phone':
                        if payload.nickname is not None:
                            raise ProfileError('Choose only the user whose phone should be cleared.')
                        setup.profiles.bind_phone(user.id, None)
                        setup.profiles.set_setup(user.id, 'phone')
                        setup.invalidate(user.id)
                        user = setup.profiles.get(user.id)
                    elif payload.action == 'remove':
                        if payload.nickname is not None:
                            raise ProfileError('Choose only the user to remove.')
                        setup.profiles.remove(user.id)
                        setup.invalidate(user.id)
                        service.personal_timers._timers.pop(user.id, None)
                        app.state.profile_calendars.accounts.pop(user.id, None)
                        return response({'removed':True})
                    else:
                        raise ProfileError('Choose a supported user-management action.')
                result = response({'profile_id':user.id, 'nickname':user.nickname,
                                   'setup_stage':user.setup_stage, 'approved':True})
                # Rename never changes who is selected on the communal wall.
                if payload.action != 'rename':
                    token, _ = setup.issue(user.id, request_origin(request))
                    # The server expires an unpaired draft in one hour. Keep
                    # the cookie long enough for its confirmed bound grant to
                    # resume after restart without asking for approval again.
                    result.set_cookie(COOKIE, token, max_age=BOUND_SECONDS, httponly=True,
                        secure=request.url.scheme == 'https', samesite='strict', path='/api/v1/user-self')
                    # Keep independent approvals on the communal wall. Opening
                    # another person's setup must not erase a previous user's
                    # timer/task grant. Neither cookie grants administration.
                    result.set_cookie(wall_cookie(user.id), token, max_age=BOUND_SECONDS, httponly=True,
                        secure=request.url.scheme == 'https', samesite='strict', path='/api/v1/user-self/wall')
                service.publish('user.profile.updated', {'profile_id':user.id})
                return result
        except ProfileError as error:
            raise HTTPException(422, str(error)) from None

    @app.get('/api/v1/user-self/status', dependencies=[Depends(local_only)])
    async def status(request: Request):
        user, check = current(request, draft=True)
        result = setup.view(user.id)
        check()
        return response(result)

    @app.post('/api/v1/user-self/lock', dependencies=[Depends(local_only)])
    async def lock(request: Request):
        user, check = current(request, draft=True)
        with setup.lock:
            check()
            setup.revoke(user.id)
        result = response({'locked':True})
        result.delete_cookie(COOKIE, path='/api/v1/user-self')
        return result

    @app.post('/api/v1/user-self/progress', dependencies=[Depends(local_only)])
    async def progress(payload: Progress, request: Request):
        user, check = current(request)
        if payload.stage not in SETUP_STAGES or payload.stage == 'phone':
            raise HTTPException(422, 'Choose a personal setup step after pairing.')
        with setup.lock:
            check()
            setup.profiles.set_setup(user.id, payload.stage, wall_share_approved=payload.wall_share_approved)
        service.publish('user.settings.updated', {'profile_id':user.id})
        return response(setup.view(user.id))

    @app.post('/api/v1/user-self/pairing/start', dependencies=[Depends(local_only)])
    async def pairing_start(request: Request):
        try:
            return response(setup.start_pairing(request.cookies.get(COOKIE), request_origin(request)))
        except ProfileError as error:
            raise HTTPException(409, str(error)) from None

    async def pairing_action(request, action):
        user, check = current(request, draft=True)
        payload = await _body(request, 2048)
        check()
        if not setup.pairing_owner or setup.pairing_owner[2] != user.id:
            raise HTTPException(409, 'Open your own pairing session first.')
        try:
            if action == 'select' and set(payload) == {'session','device'}:
                return response(setup.pairing.select(payload['session'], payload['device']))
            if action == 'confirm' and set(payload) == {'session','challenge','accepted'} and type(payload['accepted']) is bool:
                return response(setup.pairing.confirm(payload['session'], payload['challenge'], payload['accepted']))
            if action == 'cancel' and set(payload) == {'session'}:
                return response(await setup.pairing.cancel(payload['session']))
        except ValueError:
            raise HTTPException(409, 'That pairing step ended. Start your own pairing again.') from None
        raise HTTPException(422, 'Pairing request is invalid.')

    @app.post('/api/v1/user-self/pairing/select', dependencies=[Depends(local_only)])
    async def pairing_select(request: Request):
        return await pairing_action(request, 'select')

    @app.post('/api/v1/user-self/pairing/confirm', dependencies=[Depends(local_only)])
    async def pairing_confirm(request: Request):
        return await pairing_action(request, 'confirm')

    @app.post('/api/v1/user-self/pairing/cancel', dependencies=[Depends(local_only)])
    async def pairing_cancel(request: Request):
        return await pairing_action(request, 'cancel')

    async def personal(request, method, path):
        user, check = current(request)
        value = await _body(request, 65536) if method != 'GET' else {}
        try:
            async with asyncio.timeout(45):
                result = await own_operation(service, SimpleNamespace(profile_id=user.id), method,
                                             '/remote/api/'+path, value, check)
            check()
            if len(json.dumps(result)) > 1024*1024:
                raise HTTPException(503, 'Your personal response is too large. Nothing was exported.')
            return response(result)
        except TimeoutError:
            raise HTTPException(503, 'Your personal request timed out. Refresh before retrying.') from None

    @app.get('/api/v1/user-self/preview', dependencies=[Depends(local_only)])
    async def preview(request: Request):
        return await personal(request, 'GET', 'preview')

    @app.patch('/api/v1/user-self/settings', dependencies=[Depends(local_only)])
    async def settings(request: Request):
        return await personal(request, 'PATCH', 'settings')

    @app.get('/api/v1/user-self/google/calendars', dependencies=[Depends(local_only)])
    async def calendars(request: Request):
        return await personal(request, 'GET', 'google/calendars')

    @app.get('/api/v1/user-self/google/colors', dependencies=[Depends(local_only)])
    async def colors(request: Request):
        return await personal(request, 'GET', 'google/colors')

    @app.post('/api/v1/user-self/google/sync', dependencies=[Depends(local_only)])
    async def sync(request: Request):
        return await personal(request, 'POST', 'google/sync')

    @app.post('/api/v1/user-self/todos/complete', dependencies=[Depends(local_only)])
    async def complete(request: Request):
        return await personal(request, 'POST', 'todos/complete')

    @app.post('/api/v1/user-self/timer', dependencies=[Depends(local_only)])
    async def timer(request: Request):
        return await personal(request, 'POST', 'command')

    @app.post('/api/v1/user-self/google/authorize', dependencies=[Depends(local_only)])
    async def authorize(request: Request):
        payload = await _body(request, 1024)
        if set(payload) - {'task_updates'} or type(payload.get('task_updates', False)) is not bool:
            raise HTTPException(422, 'Choose read-only or task-update consent.')
        try:
            return response(setup.desktop.begin(request.cookies.get(COOKIE), request_origin(request),
                                                task_updates=payload.get('task_updates', False)))
        except ValueError as error:
            raise HTTPException(422, str(error)) from None

    @app.post('/api/v1/user-self/remote/issue', dependencies=[Depends(local_only)])
    async def remote_issue(request: Request):
        user, check = current(request)
        payload = await _body(request, 1024)
        if payload:
            raise HTTPException(422, 'Remote enrollment request is invalid.')
        if not setup.profiles.remote_allowed(user.id):
            raise HTTPException(403, 'This hub restricts phone remotes to the primary user. Your local personal setup still works.')
        try:
            status = await tailscale_request({'action':'status'})
        except Exception:
            raise HTTPException(503, 'Private phone transport is unavailable. You can skip remote setup and try later.') from None
        url = status.get('command_url')
        if not isinstance(url, str) or not url.endswith('/command'):
            raise HTTPException(409, 'The primary user needs to enable private Tailscale HTTPS first. You can skip remote setup.')
        try:
            origin = private_origin(url.removesuffix('/command'))
            with setup.lock:
                check()
                ticket = app.state.companion.issue_for_setup(origin, user.id, check)
            url = origin+'/remote/#enroll='+ticket
            qr = await qr_data(url)
            check()
            return response({'url':url, 'qr':qr, 'expires_in_seconds':300})
        except CompanionDenied as error:
            raise HTTPException(403, str(error)) from None
        except ValueError:
            raise HTTPException(409, 'Private phone access is not configured. You can skip this step.') from None

    @app.get('/api/v1/user-self/remote/pending', dependencies=[Depends(local_only)])
    async def remote_pending(request: Request):
        user, check = current(request)
        try:
            with setup.lock:
                return response({'pending':app.state.companion.pending_for_setup(user.id, check)})
        except CompanionDenied as error:
            raise HTTPException(403, str(error)) from None

    @app.post('/api/v1/user-self/remote/approve', dependencies=[Depends(local_only)])
    async def remote_approve(request: Request):
        user, check = current(request)
        payload = await _body(request, 1024)
        if set(payload) != {'device_id','comparison_code'}:
            raise HTTPException(422, 'Compare the code on your phone before approving.')
        try:
            with setup.lock:
                check()
                app.state.companion.approve_for_setup(user.id, payload['device_id'], payload['comparison_code'], check)
            return response({'approved':True})
        except CompanionDenied as error:
            raise HTTPException(403, str(error)) from None

    @app.get('/api/v1/user-self/google/callback', dependencies=[Depends(local_only)])
    async def callback(request: Request):
        try:
            await asyncio.to_thread(setup.desktop.finish, request.cookies.get(COOKIE),
                                    request_origin(request), request.url.query)
            target = '/?setup=personal'
        except Exception:
            target = '/?setup=personal&google_error=1'
        return RedirectResponse(target, status_code=303,
                                headers={'Cache-Control':'no-store', 'Referrer-Policy':'no-referrer'})

    return setup

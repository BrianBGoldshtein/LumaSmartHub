"""Independent primary-approved wall controls, bound to each user's phone.

Cookie tokens stay HttpOnly. A profile selector is never authority: the grant
must resolve to that exact account and original live ANCS generation. Fixed
routes expose only timers and shared-task actions, not settings or calendars.
"""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace

from fastapi import Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from .admin_api import request_origin
from .companion_api import _body
from .companion_profiles import own_operation
from .models import DisplayPower
from .profiles import ProfileError
from .user_setup import SetupDenied, wall_cookie


def install_user_wall_api(app, service, setup, local_only):
    def response(value):
        return JSONResponse(value, headers={'Cache-Control': 'no-store'})

    def current(request, uid, *, tasks=False):
        try:
            name = wall_cookie(uid)
        except ProfileError:
            raise SetupDenied() from None
        user, granted = setup.recheck(request.cookies.get(name), request_origin(request))
        if user.id != uid:
            raise SetupDenied()

        def check():
            granted()  # Includes the original authorization generation.
            service._sync_sleep(datetime.now(UTC))
            if (service.state.forced_private or service.state.display_power != DisplayPower.ON or
                    service.presence_update_busy or service.presence_update_pending or
                    service.display_state and (service.display_state['awaiting_clock'] or service.display_state['mode'] != 'day')):
                raise SetupDenied()
            if tasks and not setup.profiles.get(user.id).wall_share_approved:
                raise SetupDenied()
        check()
        return user, check

    def preview(user):
        # Do not return calendar/task data through a timer dialog, especially
        # for a present person who did not consent to shared calendar panels.
        return {'profile_id': user.id, 'nickname': user.nickname,
                'timer': service.personal_timers.for_user(user.id).snapshot()}

    @app.get('/api/v1/user-self/wall/access', dependencies=[Depends(local_only)])
    async def access(request: Request):
        allowed = []
        for candidate in setup.profiles.list():
            try:
                user, check = current(request, candidate.id)
                check()
                allowed.append({'profile_id': user.id, 'nickname': user.nickname})
            except SetupDenied:
                continue
        return response({'users': allowed})

    @app.get('/api/v1/user-self/wall/preview', dependencies=[Depends(local_only)])
    async def read(request: Request, profile_id: str):
        user, check = current(request, profile_id)
        result = preview(user)
        check()
        return response(result)

    async def operation(request, path):
        payload = await _body(request, 65536)
        uid = payload.pop('profile_id', None)
        user, check = current(request, uid, tasks=path == 'todos/complete')
        try:
            async with asyncio.timeout(45):
                result = await own_operation(service, SimpleNamespace(profile_id=user.id), 'POST',
                                             '/remote/api/'+path, payload, check)
            check()
            if path == 'command':
                return response({'result': result['result'], 'preview': preview(user)})
            return response({'changed': True})
        except TimeoutError:
            raise HTTPException(503, 'Your personal request timed out. Refresh before retrying.') from None

    @app.post('/api/v1/user-self/wall/timer', dependencies=[Depends(local_only)])
    async def timer(request: Request):
        return await operation(request, 'command')

    @app.post('/api/v1/user-self/wall/todos/complete', dependencies=[Depends(local_only)])
    async def complete(request: Request):
        return await operation(request, 'todos/complete')

    @app.post('/api/v1/user-self/wall/lock', dependencies=[Depends(local_only)])
    async def lock(request: Request):
        payload = await _body(request, 1024)
        if set(payload) != {'profile_id'}:
            raise HTTPException(422, 'Choose only your personal controls.')
        user, check = current(request, payload['profile_id'])
        with setup.lock:
            check()
            setup.revoke(user.id)
        result = response({'locked': True})
        result.delete_cookie(wall_cookie(user.id), path='/api/v1/user-self/wall')
        return result

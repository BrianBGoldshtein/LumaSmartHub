"""Own-account remote operations: never proxy a guest to primary controllers."""
from __future__ import annotations

import asyncio
import re

from fastapi import HTTPException

from .focus_timer import TIMER_COMMANDS
from .integrations.google_calendar import TaskConflict, calendar_failure_status
from .profiles import PERSONAL_KEYS, PRIMARY_ID, ProfileError
from .serde import to_primitive


PERSONAL_ROUTES = frozenset({
    ('GET', '/remote/api/preview'), ('GET', '/remote/api/settings'),
    ('PATCH', '/remote/api/settings'), ('POST', '/remote/api/command'),
    ('GET', '/remote/api/google/status'), ('GET', '/remote/api/google/calendars'),
    ('GET', '/remote/api/google/colors'), ('POST', '/remote/api/google/sync'),
    ('POST', '/remote/api/todos/complete'),
})


def own_settings(service, uid):
    user = service.profiles.get(uid)
    return {**user.personal, 'theme': service.settings.theme.value,
            'timezone': service.settings.timezone,
            'weather_location_label': service.settings.weather_location_label}


def own_preview(service, uid):
    # The room snapshot supplies only explicitly public clock/weather/style.
    # All private fields come from this user's projection, never flat primary.
    room = service.snapshot()
    account = service.profile_calendars.projection(uid)
    if account is None:
        raise HTTPException(403, 'Connect this user’s authorized iPhone first.')
    user = service.profiles.get(uid)
    return {'server_time': room['server_time'], 'privacy_redacted': False,
            'profile_id': uid, 'nickname': user.nickname, 'role': user.role,
            'weather': room['weather'], 'settings': {key: own_settings(service, uid)[key]
                for key in ('theme', 'timezone', 'weather_location_label')},
            'state': {'active_page': room['state']['active_page'],
                      'display_power': room['state']['display_power'], 'phone_connected': True},
            'timer': service.personal_timers.for_user(uid).snapshot(),
            **{key: account[key] for key in ('calendar', 'ongoing', 'todos', 'todo_controls', 'departure')}}


async def own_operation(service, principal, method, path, value, recheck):
    uid = principal.profile_id
    if (method, path) not in PERSONAL_ROUTES:
        raise HTTPException(403, 'This feature is restricted to the primary user.')
    account = service.profile_calendars.account(uid)
    recheck()
    if path == '/remote/api/preview':
        return own_preview(service, uid)
    if path == '/remote/api/settings':
        if method == 'PATCH':
            if not value or value.keys() - PERSONAL_KEYS:
                raise HTTPException(403, 'Only your personal calendar and reminder settings can be changed here.')
            async with account.lock:
                recheck()
                try:
                    service.profiles.update_personal(uid, value)
                except ProfileError:
                    raise HTTPException(422, 'Personal calendar or reminder settings are invalid.') from None
                if uid == PRIMARY_ID:
                    service.machine.settings = service.storage.load_settings()
                service.publish('user.settings.updated', {'profile_id': uid})
        return own_settings(service, uid)
    if path == '/remote/api/command':
        if (set(value) - {'name', 'value'} or not isinstance(value.get('name'), str)
                or value['name'] not in TIMER_COMMANDS):
            raise HTTPException(403, 'Secondary users can control their own timers, not hub-wide commands.')
        recheck()
        timer = service.personal_timers.for_user(uid)
        try:
            result = timer.execute(value['name'], value.get('value'), focus=service.settings.timer_focus_minutes,
                                   rest=service.settings.timer_break_minutes, source='phone_remote')
        except ValueError:
            raise HTTPException(422, 'Use a timer from 1 second to 4 hours with a short title.') from None
        service.publish('user.timer.updated', {'profile_id': uid})
        return {'result': to_primitive(result), 'preview': own_preview(service, uid)}
    if path == '/remote/api/google/status':
        return {'configured': account.google.configured(), 'authorized': account.google.authorized(),
                'task_updates': account.google.task_write_authorized(), **account.status}
    if path == '/remote/api/google/sync':
        if value:
            raise HTTPException(422, 'Remote request is invalid.')
        try:
            return await service.profile_calendars.sync(uid, recheck=recheck)
        except (HTTPException, PermissionError):
            raise
        except Exception:
            raise HTTPException(503, 'Your Google calendar could not sync. Saved events remain on Luma.') from None
    if path == '/remote/api/todos/complete':
        if (set(value) != {'calendar_id', 'event_id', 'etag', 'completed'}
                or not isinstance(value['calendar_id'], str) or not 1 <= len(value['calendar_id']) <= 1024
                or not isinstance(value['event_id'], str) or not re.fullmatch(r'[A-Za-z0-9_]{1,1024}', value['event_id'])
                or not isinstance(value['etag'], str) or not re.fullmatch(r'[^\r\n]{1,256}', value['etag'])
                or type(value['completed']) is not bool):
            raise HTTPException(422, 'Remote request is invalid.')
        try:
            await service.profile_calendars.complete_task(uid, recheck=recheck, **value)
        except TaskConflict:
            raise HTTPException(409, 'This task changed. Refresh before trying again.') from None
        except ValueError:
            raise HTTPException(422, 'Choose your to-do calendar and completed color before changing a task.') from None
        except (HTTPException, PermissionError):
            raise
        except Exception as error:
            if not account.status['reconnect_required']:
                account.status.update(calendar_failure_status(error))
            raise HTTPException(503, 'Your Google task could not be updated. Refresh before trying again.') from None
        return own_preview(service, uid)
    if path in {'/remote/api/google/calendars', '/remote/api/google/colors'}:
        async with account.lock:
            recheck()
            try:
                async with service.profile_calendars.provider_slots:
                    recheck()
                    provider = account.google.list_calendars if path.endswith('/calendars') else account.google.event_colors
                    result = await asyncio.to_thread(provider)
                recheck()
                return result
            except HTTPException:
                raise
            except Exception as error:
                if not account.status['reconnect_required']:
                    account.status.update(calendar_failure_status(error))
                raise HTTPException(503, 'Your Google calendar is unavailable. Saved events remain on Luma.') from None
    raise HTTPException(403, 'This remote operation is not available.')

"""Account selection for local read-only speech, never speaker authentication."""
from __future__ import annotations

from datetime import UTC, datetime
import re
import secrets
from time import monotonic
from zoneinfo import ZoneInfo

from .briefing import morning_briefing
from .calendar_logic import ongoing_events, todo_events, todo_view, visible_events
from .models import CommandName, DisplayPower
from .serde import to_primitive
from .voice import parse_local_command
from .voice_library import answer_query

PERSONAL_QUERIES = frozenset({'next_event', 'calendar_today', 'remaining_today', 'calendar_tomorrow',
    'ongoing', 'calendar_week', 'next_location', 'free_time', 'tasks_today', 'tasks_due', 'tasks_soon',
    'tasks_overdue', 'tasks_completed', 'phone_status', 'privacy_status', 'sync_status'})
UNAVAILABLE = 'That person’s information is private. Connect their authorized phone and approve sharing on the hub first.'


def split_account_phrase(text: str, names: dict[str, str]):
    """Return stripped phrase and explicit account, using only bounded syntax.

    A name is context, not authorization. Never infer one from a substring in
    an event/timer title, nor silently turn an unknown possessive into "my".
    """
    text = re.sub(r'\s+', ' ', text.strip().casefold().replace('’', "'"))
    text = re.sub(r'^(?:hey\s+)?luma[,.]?\s*', '', text)
    personal_syntax = bool(re.match(r'^(?:what|when|where|why|how|is|are|do|read|tell|good morning)\b', text))
    matches = []
    for uid, name in names.items():
        name = re.sub(r'\s+', ' ', name.casefold().replace('’', "'"))
        escaped = re.escape(name)
        if text.strip(' ,.!?') == name:
            matches.append((uid, ''))
            continue
        prefix = re.match(r'^'+escaped+r'(?:\s*[,.:]\s*|\s+)(?=(?:what|when|where|why|how|is|are|do|read|tell|good morning|change|set|start|stop|pause|resume|cancel|wake|turn|hide|show)\b)', text)
        suffix = re.search(r'\s+for\s+'+escaped+r'[.!?]*$', text) if personal_syntax else None
        possessive = re.search(r'(?<!\w)'+escaped+r"'s\s+(?=(?:calendars?|schedule|agenda|tasks|to do|next|timer|phone|iphone)\b)", text) if personal_syntax else None
        if prefix:
            matches.append((uid, text[prefix.end():]))
        elif suffix:
            matches.append((uid, text[:suffix.start()]))
        elif possessive:
            matches.append((uid, text[:possessive.start()]+'my '+text[possessive.end():]))
    if len(matches) != 1:
        if matches:
            return text, None, True
        unknown = personal_syntax and bool(re.search(r"\b(?!(?:what|when|where|how|it)\b)[\w-]+'s\s+(?:calendars?|schedule|agenda|tasks|next|timer|phone|iphone)\b", text))
        unknown_suffix = re.search(r'\s+for\s+([\w][\w -]{0,39})[.!?]*$', text)
        if personal_syntax and unknown_suffix and unknown_suffix[1] not in {'today', 'tomorrow', 'tonight', 'this week', 'the week',
                'this afternoon', 'this evening', 'now', 'right now', 'next week', 'next month'}:
            unknown = True
        return text, None, unknown
    uid, stripped = matches[0]
    # Explicitly naming two accounts is not one person's question.
    if re.search(r"\b(?!(?:what|when|where|how|it)\b)[\w-]+'s\b", stripped):
        return text, None, True
    return stripped, uid, True


class VoiceAccounts:
    def __init__(self, service, *, clock=monotonic):
        self.service, self.clock = service, clock
        self.pending = None
        self.reply_job = None

    def names(self):
        return {user.id: user.nickname for user in self.service.profiles.list()} if self.service.profiles else {}

    def eligible(self, *, briefing=False, now=None):
        service, now = self.service, now or datetime.now(UTC)
        service._sync_sleep(now)
        if (not service.settings.voice_enabled or service.state.forced_private or
            service.state.display_power != DisplayPower.ON or service.presence_update_busy or
            service.presence_update_pending or (service.display_state and
            (service.display_state['awaiting_clock'] or (not briefing and service.display_state['mode'] != 'day')))):
            return {}
        eligible = {}
        if service.profiles and service.user_bluetooth:
            for user in service.profiles.list():
                phone = service.user_bluetooth.companion_presence(user.id)
                if user.wall_share_approved and phone.authorized and phone.address == user.phone_address and phone.generation:
                    eligible[user.id] = phone.generation
            # Preserve the existing explicit local primary PIN privacy override.
            # It never authorizes a secondary's private data or replaces ANCS.
            if 'primary' not in eligible and service.primary_private_visible(now, briefing=briefing):
                until = service.state.pin_unlocked_until
                if until and until > now:
                    eligible['primary'] = 'pin:'+until.isoformat()
        return eligible

    def clear(self):
        changed = self.pending is not None
        self.pending = self.reply_job = None
        if changed:
            self.service.publish('voice.account.updated')

    def view(self, now=None):
        pending = self.pending
        if not pending:
            return None
        eligible = self.eligible(briefing=pending['intent'] == 'morning', now=now)
        allowed = {uid: generation for uid, generation in pending['eligible'].items()
                   if eligible.get(uid) == generation}
        if self.clock() >= pending['until'] or not allowed:
            self.clear()
            return None
        names = self.names()
        return {'id': pending['id'], 'remaining_ms': max(0, int((pending['until']-self.clock())*1000)),
                'users': [{'profile_id': uid, 'nickname': names[uid]} for uid in allowed if uid in names]}

    def _snapshot(self, uid, generation, *, briefing=False, now=None):
        service, now = self.service, now or datetime.now(UTC)
        if self.eligible(briefing=briefing, now=now).get(uid) != generation:
            return None
        account = service.profile_calendars.account(uid)
        settings = service.profile_calendars.settings(uid)
        room = service.snapshot(now, briefing=briefing)
        day = now.astimezone(ZoneInfo(settings.timezone)).replace(hour=0, minute=0, second=0, microsecond=0)
        selected = dict(calendar_ids=set(settings.visible_calendar_ids), sleep_calendar_ids=set(settings.sleep_calendar_ids),
                        sleep_title=settings.sleep_event_title)
        all_events = [event for event in visible_events(account.events, now=day, **selected) if not event.self_declined]
        visible = visible_events(account.events, now=now, **selected)
        tasks = todo_events(account.events, todo_calendar_id=settings.todo_calendar_id, now=now)
        task_view = lambda rows: to_primitive(sorted((todo_view(event, settings.todo_completed_color_id) for event in rows),
            key=lambda row: (row['completed'], row['due_date'], row['summary'].casefold(), row['id'])))
        view = {'server_time': now.isoformat(), 'settings': {**to_primitive(settings),
                'phone_address': service.profiles.get(uid).phone_address}, 'display': room['display'],
                'state': {'phone_connected': not generation.startswith('pin:')}, 'privacy_redacted': False,
                'weather': room['weather'], 'calendar': to_primitive(visible), 'ongoing': to_primitive(ongoing_events(visible, now)),
                'todos': task_view(tasks), 'timer': service.personal_timers.for_user(uid).snapshot(),
                'voice_calendar': {'authorized': account.google.authorized(),
                    'fresh': service.calendar_is_fresh(now) if uid == 'primary' else service.profile_calendars.fresh(uid, now),
                    'events': to_primitive(all_events)},
                'voice_todos': task_view(event for event in account.events if event.calendar_id == settings.todo_calendar_id
                    and event.all_day and event.status != 'cancelled')[:100]}
        return view if self.eligible(briefing=briefing, now=now).get(uid) == generation else None

    def answer(self, uid, generation, intent):
        view = self._snapshot(uid, generation, briefing=intent == 'morning')
        if view is None:
            return {'accepted': False, 'message': UNAVAILABLE}
        message = morning_briefing(view) if intent == 'morning' else answer_query(intent, view)
        if self.eligible(briefing=intent == 'morning').get(uid) != generation:
            return {'accepted': False, 'message': UNAVAILABLE}
        return {'accepted': True, 'message': message}

    def handle(self, text):
        stripped, uid, named = split_account_phrase(text, self.names())
        if self.pending and stripped.strip(' .!?') in {'cancel', 'never mind', 'nevermind'}:
            self.clear()
            return {'accepted': False, 'message': 'Cancelled', 'speak': False}
        if named and not stripped and uid:
            pending = self.pending
            if pending and self.view():
                return self.select(pending['id'], uid, enqueue=False)
            return {'accepted': False, 'message': 'Ask a personal question and name the person to use.'}
        parsed = parse_local_command(stripped)
        intent = 'morning' if parsed and parsed.name == CommandName.GOOD_MORNING else str(parsed.value) if parsed and parsed.name == CommandName.LOCAL_QUERY else None
        if intent not in PERSONAL_QUERIES and intent != 'morning' and not (named and intent == 'timer_status'):
            self.clear()
            if named and intent and (intent in {'time', 'date', 'internet_status', 'help', 'jacket'} or
                intent.startswith(('weather', 'rain_', 'high_', 'low_'))):
                # Clock/forecast facts do not require an account. Naming one
                # must not turn those public questions into a private read.
                view = self.service.snapshot()
                return {'accepted': True, 'message': answer_query(intent, view)}
            if named:
                return {'accepted': False, 'message': 'Unknown command', 'speak': False}
            return None
        self.clear()
        if named and uid is None:
            return {'accepted': False, 'message': UNAVAILABLE}
        eligible = self.eligible(briefing=intent == 'morning')
        if named:
            if uid not in eligible:
                return {'accepted': False, 'message': UNAVAILABLE}
            return self.answer(uid, eligible[uid], intent)
        if not eligible:
            # The old public morning greeting is still useful without phones.
            if intent == 'morning':
                view = self.service.snapshot(briefing=True)
                view = {**view, 'privacy_redacted': True, 'calendar': []}
                return {'accepted': True, 'message': morning_briefing(view)}
            return {'accepted': False, 'message': UNAVAILABLE}
        if len(eligible) == 1:
            uid, generation = next(iter(eligible.items()))
            return self.answer(uid, generation, intent)
        self.pending = {'id': secrets.token_urlsafe(32), 'until': self.clock()+30,
                        'intent': intent, 'eligible': eligible}
        self.service.publish('voice.account.updated')
        return {'accepted': False, 'message': 'Whose information should I use? Say Hey Luma and a name, or choose on the screen.'}

    def select(self, choice_id, uid, *, enqueue=True):
        pending = self.pending
        if not pending or not self.view() or not secrets.compare_digest(pending['id'], choice_id):
            return {'accepted': False, 'message': 'That choice expired. Ask your question again.', 'speak': False}
        eligible = self.eligible(briefing=pending['intent'] == 'morning')
        if uid not in pending['eligible'] or eligible.get(uid) != pending['eligible'][uid]:
            return {'accepted': False, 'message': UNAVAILABLE, 'speak': False}
        intent, generation = pending['intent'], pending['eligible'][uid]
        self.clear()
        if enqueue:
            # Queue an intent, NOT a generated private reply. The device claims
            # it once and rechecks the original ANCS/PIN generation at that time.
            self.reply_job = {'uid': uid, 'generation': generation, 'intent': intent, 'until': self.clock()+10}
            return {'accepted': True, 'message': 'Answer queued', 'speak': False}
        return self.answer(uid, generation, intent)

    def claim_reply(self):
        job, self.reply_job = self.reply_job, None
        if not job or self.clock() >= job['until']:
            return {'play': False}
        response = self.answer(job['uid'], job['generation'], job['intent'])
        return {'play': True, **response} if response['accepted'] else {'play': False}

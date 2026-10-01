"""Bounded local spoken answers. No model, network, or paid service calls."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import math
import re

from .voice_model import match


QUERY_PHRASES = {
    'next_departure': ('when is my next departure', 'when is the next departure', 'what is my next departure', 'next departure'),
    'weather_today': ('what is the weather today', "what's the weather today", 'what is the forecast today', 'how is the weather today'),
    'weather_now': ('what is the weather', "what's the weather", 'what is the temperature', 'how hot is it', 'how cold is it', 'what is the weather right now'),
    'weather_tomorrow': ('what is the weather tomorrow', "what's the weather tomorrow", 'what is the forecast tomorrow', 'how is the weather tomorrow', "how's the weather tomorrow", "what's it like outside tomorrow", 'how warm will it be tomorrow', "tell me tomorrow's forecast"),
    'weather_afternoon': ('what is the weather this afternoon', 'what is the forecast this afternoon', 'how warm this afternoon'),
    'weather_evening': ('what is the weather this evening', "what's the weather tonight", 'what is the forecast tonight', 'how cold tonight'),
    'rain_today': ('will it rain today', 'is it going to rain today', 'do i need an umbrella', 'what is the chance of rain today'),
    'rain_tomorrow': ('will it rain tomorrow', 'what is the chance of rain tomorrow', 'do i need an umbrella tomorrow'),
    'rain_timing': ('when will it rain', 'when is the next rain', 'when should i expect rain'),
    'high_today': ('what is the high today', 'how hot will it get today'),
    'low_today': ('what is the low today', 'how cold will it get today'),
    'high_tomorrow': ('what is the high tomorrow', 'how hot will it get tomorrow'),
    'low_tomorrow': ('what is the low tomorrow', 'how cold will it get tomorrow'),
    'jacket': ('do i need a jacket', 'should i bring a jacket', 'do i need a coat today'),
    'next_event': ('when is my next event', "when's my next event", 'what is my next event', "what's my next event", 'what is next on my calendar', 'when is my next appointment'),
    'calendar_today': ('what is on my calendar today', "what's on my calendar today", "what's on my agenda today", 'what is my schedule today', 'what do i have today', 'what do i have going on today', 'read my calendar today'),
    'remaining_today': ('do i have anything else today', 'what else is on my calendar today', 'what is left on my calendar today'),
    'calendar_tomorrow': ('what is on my calendar tomorrow', "what's on my calendar tomorrow", 'what is my schedule tomorrow', 'what do i have tomorrow'),
    'ongoing': ('what is happening now', 'what event is happening now', 'am i in an event right now'),
    'calendar_week': ('what is on my calendar this week', 'what is coming up this week', 'what is my week like'),
    'next_location': ('where is my next event', 'where is my next appointment', 'where do i need to go next'),
    'free_time': ('when am i free', 'how long am i free', 'when is my next free block'),
    'tasks_today': ('what are my tasks today', 'what is on my to do list', "what's on my to do list", 'read my tasks'),
    'tasks_due': ('what tasks are due today', 'what is due today'),
    'tasks_soon': ('what tasks are due soon', 'what do i need to finish soon', 'what is due in the next few days'),
    'tasks_overdue': ('what tasks are overdue', "what's overdue", 'what did i miss', 'what to dos are overdue'),
    'tasks_completed': ('what tasks have i completed', 'what is done on my to do list', 'what have i finished today'),
    'time': ('what time is it', 'what time is it now', "what's the time", "what's the time now", 'what is the time',
             'tell me the time', 'could you tell me the time', 'could you tell me the time now', 'do you know what time it is'),
    'date': ('what day is it', 'what is the date today', "what's the date today"),
    'timer_status': ('how much time is left', 'how much time is left on my timer', 'what is my timer status'),
    'phone_status': ('is my phone connected', 'can you see my iphone', 'is my iphone nearby'),
    'privacy_status': ('is luma private', 'is privacy mode on', 'why is my calendar hidden', 'can i see my calendar'),
    'internet_status': ('is the internet working', 'are you online', 'what is the wifi status'),
    'sync_status': ('is my calendar up to date', 'when did weather update', 'are my calendars syncing'),
    'help': ('what can you do', 'what can i say', 'help', 'voice commands'),
}

LIBRARY = [
    {'title':'Transit', 'examples':['Show transit', 'When is my next departure?']},
    {'title':'Weather', 'examples':['What’s the weather today?', 'What’s the weather tomorrow?', 'Will it rain tomorrow?', 'What is the high tomorrow?', 'Do I need a jacket?']},
    {'title':'Calendar', 'examples':['When is my next event?', 'What’s on my calendar today?', 'Do I have anything else today?', 'What’s on my calendar tomorrow?', 'What is happening now?', 'When am I free?']},
    {'title':'Tasks & time', 'examples':['What are my tasks today?', 'What tasks are overdue?', 'What time is it?', "What's the time?", 'What day is it?', 'How much time is left on my timer?']},
    {'title':'Luma status', 'examples':['Is my phone connected?', 'Is the internet working?', 'Why is my calendar hidden?', 'Is my calendar up to date?']},
    {'title':'Everyday controls', 'examples':['Start focus timer', 'Pause timer', 'Good morning', 'Good night', 'Screen off', 'Wake screen', 'Change brightness', 'Change theme to arcade', 'Hide my calendar', 'What can I say?']},
    {'title':'Room scenes', 'examples':['Run morning scene', 'Run night scene', 'Run arrival scene', 'Run away scene', 'Cancel scene']},
]


def normalize(text):
    text=text.casefold().replace('’', "'")
    text=re.sub(r"\bwhat's\b", 'what is', text)
    text=re.sub(r'[^\w\s-]', ' ', text)
    text=re.sub(r'\s+', ' ', text).strip()
    return re.sub(r'^please | please$', '', text)


ALIASES={normalize(phrase):intent for intent,phrases in QUERY_PHRASES.items() for phrase in phrases}


def query_intent(text):
    normalized=normalize(text)
    exact=ALIASES.get(normalized)
    if exact:return exact
    if not re.match(r'^(?:please )?(?:what|when|where|why|how|is|are|will|do|does|can|tell|give|check|list|read|forecast)\b',normalized):
        return None
    # The model maps wording to an answer, not to a write/device action.
    # Unsupported time horizons must never be silently changed to "today".
    if re.search(r'\b(next week|next month|yesterday|last week|december|january)\b',normalized):
        if 'weather' in normalized or 'forecast' in normalized:
            return 'weather_beyond_forecast'
        return None
    candidate=match(normalized)
    if not candidate:return None
    if candidate.startswith('action:'):return None
    tomorrow='tomorrow' in normalized or 'tomorrows' in normalized
    if tomorrow:
        candidate={'weather_today':'weather_tomorrow','weather_now':'weather_tomorrow',
                   'rain_today':'rain_tomorrow','high_today':'high_tomorrow','low_today':'low_tomorrow',
                   'calendar_today':'calendar_tomorrow'}.get(candidate,candidate)
    elif candidate in {'weather_tomorrow','rain_tomorrow','high_tomorrow','low_tomorrow','calendar_tomorrow'}:
        return None
    return candidate


def _text(value, limit=64):
    # Calendar titles are inert text, never instructions/markup/arguments.
    return re.sub(r'\s+', ' ', re.sub(r'[\x00-\x1f\x7f]', ' ', str(value))).strip()[:limit] or 'Untitled event'


def _time(value):
    return value.strftime('%I:%M %p').lstrip('0')


def _event(event, zone, today):
    start=datetime.fromisoformat(event['start']).astimezone(zone)
    when='all day' if event['all_day'] else f'at {_time(start)}'
    if start.date()!=today:
        when+=f" on {start.strftime('%A, %B')} {start.day}"
    return f"{_text(event['summary'])}, {when}."


def _list(items, render):
    return ' '.join(render(item) for item in items[:3])+(f' And {len(items)-3} more.' if len(items)>3 else '')


def _hours(weather, zone, day, *, after=None, start_hour=0, end_hour=24):
    return [hour for hour in weather.get('hourly', [])
            if (moment := datetime.fromisoformat(hour['time']).astimezone(zone)).date() == day
            and start_hour <= moment.hour < end_hour and (after is None or moment >= after)]


def _rain_chance(hours):
    values = [hour['precipitation_probability'] for hour in hours
              if hour.get('precipitation_probability') is not None]
    return max(values) if values else None


def _on_day(event, day, zone):
    return (datetime.fromisoformat(event['start']).astimezone(zone).date() <= day
            and datetime.fromisoformat(event['end']).astimezone(zone) > datetime.combine(day, datetime.min.time(), zone))


def answer_query(intent, snapshot):
    if intent=='weather_beyond_forecast':
        return 'My detailed local forecast reaches only two days ahead. Ask about today or tomorrow.'
    if intent not in QUERY_PHRASES:
        return 'That question is not in my local library. Say, Hey Luma, what can I say?'
    if intent=='help':
        return 'Ask about weather today or tomorrow, rain, your next event, free time, tasks, your timer, phone or internet status. You can also change the theme, open a screen, start a timer, or run a configured room scene. Find examples in Hey Luma setup. I answer locally, without an AI service.'
    if (snapshot.get('display') or {}).get('awaiting_clock'):
        return 'My clock is still syncing. Please try again once the time is set.'
    zone=ZoneInfo(snapshot['settings']['timezone'])
    now=datetime.fromisoformat(snapshot['server_time']).astimezone(zone)
    if intent=='time': return f"It is {_time(now)}."
    if intent=='date': return f"Today is {now.strftime('%A, %B')} {now.day}, {now.year}."
    if intent=='phone_status':
        if snapshot['state']['phone_connected']:
            return 'Your paired iPhone is connected and its notification access is verified.'
        if snapshot['settings'].get('phone_address'):
            return 'Your paired iPhone is not currently authorized. Luma periodically attempts to reconnect; private information stays hidden.'
        return 'No iPhone is selected. Pair one in Device setup to use it as the privacy key.'
    if intent=='privacy_status':
        if snapshot['privacy_redacted']:
            return 'Private standby is on. Your paired phone is not verified, or your temporary PIN unlock expired.'
        if snapshot['state']['phone_connected']:
            return 'Private standby is off because your paired phone is verified.'
        return 'Private standby is off for a temporary local unlock. It will expire automatically.'
    if intent=='internet_status':
        state=snapshot.get('voice_status',{}).get('network',{}).get('state','unknown')
        return {
            'online':'The internet check is online.',
            'offline':'The internet check is offline. Saved information may be out of date.',
            'portal':'Wi-Fi needs a captive-portal sign-in before internet access works.',
            'limited':'Wi-Fi has limited internet access.',
        }.get(state,'I cannot verify internet access right now. Check Wi-Fi in Device setup.')
    if intent=='sync_status':
        weather=snapshot.get('weather')
        forecast='The saved weather may be out of date.' if not weather or weather.get('stale') else 'Weather is current.'
        if snapshot['privacy_redacted']:
            return forecast+' Calendar status is hidden in private standby.'
        calendar='Calendar is current.' if snapshot.get('voice_calendar',{}).get('fresh') else 'Calendar is using saved information.'
        return calendar+' '+forecast
    if intent=='next_departure':
        choices=[]
        for stop in snapshot.get('transit',[]):
            if snapshot['privacy_redacted'] and not stop['public']:continue
            for row in stop['departures']:
                at=datetime.fromisoformat(row['at'])
                if at>=now:choices.append((at,stop,row))
        if not choices:return 'No departure times are visible right now. Add a stop in Transit setup, or unlock private information and try again.'
        at,stop,row=min(choices,key=lambda item:item[0])
        minutes=max(0,math.ceil((at-now).total_seconds()/60))
        timing='now' if minutes==0 else f"in {minutes} {'minute' if minutes==1 else 'minutes'}"
        kind='prediction' if row['kind']=='predicted' else 'schedule'
        prefix=f"From a saved {kind}, which may be out of date: " if row['stale'] else 'Scheduled: ' if kind=='schedule' else ''
        return prefix+f"{_text(row['route'])} to {_text(row['destination'] or row['direction'] or 'its destination')}, from {_text(stop['title'])}, {timing}."
    if intent=='timer_status':
        timer=snapshot.get('timer')
        if not timer or timer['status']=='idle': return 'There is no active timer.'
        if timer['status']=='complete': return 'Your timer is finished.'
        seconds=math.ceil(timer.get('remaining_seconds',0))
        minutes,seconds=divmod(max(0,seconds),60)
        return f"Your timer {'is paused with' if timer['status']=='paused' else 'has'} {minutes} {'minute' if minutes==1 else 'minutes'} and {seconds} {'second' if seconds==1 else 'seconds'} left."
    if intent.startswith('weather') or intent.startswith('rain_') or intent.startswith(('high_', 'low_')) or intent=='jacket':
        weather=snapshot.get('weather')
        if not weather: return 'I do not have a saved forecast yet. Set your location and connect to the internet in setup.'
        observed=datetime.fromisoformat(weather['observed_at']).astimezone(zone)
        old=weather['stale'] or observed.date()!=now.date()
        prefix=f"My last saved forecast is from {observed.strftime('%B')} {observed.day} at {_time(observed)}; it may be out of date. " if old else ''
        if intent in {'rain_today','rain_tomorrow'}:
            day=now.date()+timedelta(days=int(intent=='rain_tomorrow'))
            hours=_hours(weather,zone,day,after=now if day==now.date() else None)
            chances=[h['precipitation_probability'] for h in hours if h.get('precipitation_probability') is not None]
            label='tomorrow' if day!=now.date() else 'the rest of today'
            if not chances: return prefix+f'I do not have precipitation probabilities for {label}.'
            return prefix+f"The highest hourly chance of precipitation in the saved forecast for {label} is {max(chances)} percent."+(' Some hours are missing.' if len(chances)<len(hours) else '')
        if intent=='rain_timing':
            for hour in weather.get('hourly',[]):
                moment=datetime.fromisoformat(hour['time']).astimezone(zone)
                chance=hour.get('precipitation_probability')
                if moment>=now and (chance is not None and chance>=50 or 51<=hour['weather_code']<=82):
                    return prefix+f"The next saved hour suggesting precipitation is {moment.strftime('%A')} at {_time(moment)}"+(f', with a {chance} percent chance.' if chance is not None else '.')
            return prefix+'I do not see a likely rain hour in the saved two-day forecast.'
        if intent in {'weather_tomorrow','high_tomorrow','low_tomorrow'}:
            hours=_hours(weather,zone,now.date()+timedelta(days=1))
            if not hours:return prefix+'I do not have enough saved forecast hours for tomorrow yet.'
            high=round(max(hour['temperature'] for hour in hours))
            low=round(min(hour['temperature'] for hour in hours))
            if intent=='high_tomorrow':return prefix+f'Tomorrow’s forecast high is about {high} degrees Fahrenheit.'
            if intent=='low_tomorrow':return prefix+f'Tomorrow’s forecast low is about {low} degrees Fahrenheit.'
            chance=_rain_chance(hours)
            return prefix+f'Tomorrow ranges from about {low} to {high} degrees Fahrenheit.'+(f' The highest hourly precipitation chance is {chance} percent.' if chance is not None else ' Rain probability is unavailable.')
        if intent in {'high_today','low_today'}:
            word='high' if intent=='high_today' else 'low'
            return prefix+f'Today’s forecast {word} is {round(weather[word])} degrees Fahrenheit.'
        if intent in {'weather_afternoon','weather_evening'}:
            afternoon=intent=='weather_afternoon'
            hours=_hours(weather,zone,now.date(),after=now,start_hour=12 if afternoon else 18,end_hour=18 if afternoon else 24)
            label='this afternoon' if afternoon else 'this evening'
            if not hours:return prefix+f'I do not have remaining saved forecast hours for {label}.'
            low=round(min(hour['temperature'] for hour in hours));high=round(max(hour['temperature'] for hour in hours))
            chance=_rain_chance(hours)
            return prefix+f'{label.capitalize()} looks about {low} to {high} degrees Fahrenheit.'+(f' The highest hourly precipitation chance is {chance} percent.' if chance is not None else ' Rain probability is unavailable.')
        if intent=='jacket':
            hours=_hours(weather,zone,now.date(),after=now)
            if not hours:return prefix+'I do not have enough remaining forecast hours to judge a layer.'
            low=round(min(hour['temperature'] for hour in hours))
            return prefix+f'The coolest remaining forecast today is about {low} degrees Fahrenheit. '+('A layer may be useful.' if low<65 else 'A heavy layer does not look necessary from temperature alone.')
        current=f"The saved temperature is {round(weather['temperature'])} degrees Fahrenheit" if old else f"It is {round(weather['temperature'])} degrees Fahrenheit"
        current+=f", {_text(weather['summary']).lower()}."
        if intent=='weather_today':
            current+=f" {'That forecast has' if old else 'Today has'} a high of {round(weather['high'])} and a low of {round(weather['low'])}."
        else: current+=f" Feels like {round(weather['apparent_temperature'])} degrees."
        return prefix+current
    if snapshot['privacy_redacted']:
        return 'Your calendar and tasks are private. Connect your nearby phone or unlock with your PIN first.'
    meta=snapshot['voice_calendar']
    tasks=intent.startswith('tasks')
    configured = snapshot['settings']['todo_calendar_id'] if tasks else snapshot['settings']['visible_calendar_ids']
    if not configured:
        return 'Choose a task calendar in Google Calendar setup first.' if tasks else 'Choose your visible calendars in Google Calendar setup first.'
    if not meta['authorized']:
        return 'Connect Google Calendar in setup first.'
    prefix='' if meta['fresh'] else 'Calendar sync is not current. From the saved calendar only: '
    if tasks:
        if intent in {'tasks_soon','tasks_overdue','tasks_completed'}:
            all_tasks=snapshot.get('voice_todos',[])
            today=now.date().isoformat()
            if intent=='tasks_soon':
                end=(now.date()+timedelta(days=3)).isoformat()
                items=[t for t in all_tasks if not t['completed'] and today<=t['due_date']<=end]
                label='outstanding tasks due in the next four days'
            elif intent=='tasks_overdue':
                items=[t for t in all_tasks if not t['completed'] and t['due_date']<today]
                label='overdue tasks in the saved calendar window'
            else:
                items=[t for t in all_tasks if t['completed'] and t['due_date']<=today]
                label='completed tasks due through today in the saved calendar window'
            if not items:return prefix+f'No {label}.'
            return prefix+f'{len(items)} {label}. '+_list(items,lambda t:f"{_text(t['summary'])}, due {t['due_date']}.")
        items=[t for t in snapshot['todos'] if not t['completed'] and (intent!='tasks_due' or t['due_date']==now.date().isoformat())]
        if not items: return prefix+('No outstanding tasks due today.' if intent=='tasks_due' else 'No outstanding tasks on today’s list.')
        return prefix+f"{len(items)} outstanding {'tasks due today' if intent=='tasks_due' else 'tasks today'}. "+_list(items,lambda t:f"{_text(t['summary'])}.")
    events=meta['events']
    if intent=='calendar_week':
        end=now+timedelta(days=7)
        items=[e for e in events if now<datetime.fromisoformat(e['end']) and datetime.fromisoformat(e['start'])<end]
        return prefix+(f'The next seven days have {len(items)} events. '+_list(items,lambda e:_event(e,zone,now.date())) if items else 'No events in the saved week ahead.')
    if intent in {'next_location','free_time'}:
        upcoming=[e for e in events if not e['all_day'] and datetime.fromisoformat(e['start'])>now]
        ongoing=[e for e in events if not e['all_day'] and datetime.fromisoformat(e['start'])<=now<datetime.fromisoformat(e['end'])]
        if intent=='next_location':
            if not upcoming:return prefix+'No upcoming timed event in the saved week ahead.'
            first=upcoming[0]
            return prefix+(f"Your next event, {_text(first['summary'])}, is at {_text(first['location'])}." if first.get('location') else f"Your next event, {_text(first['summary'])}, has no location saved.")
        if ongoing:
            end=max(datetime.fromisoformat(e['end']) for e in ongoing)
            return prefix+f"Your current event runs until {_time(end.astimezone(zone))}."
        if upcoming:
            start=datetime.fromisoformat(upcoming[0]['start']).astimezone(zone)
            minutes=max(0,math.floor((start-now).total_seconds()/60))
            return prefix+f"You are free for about {minutes} minutes, until {_time(start)}."
        return prefix+'No upcoming timed event is saved for the next week.'
    if intent=='next_event':
        items=[e for e in events if datetime.fromisoformat(e['start'])>now]
        return prefix+('Your next event is '+_event(items[0],zone,now.date()) if items else 'No upcoming event in the saved week ahead.')
    if intent=='remaining_today':
        items=[e for e in events if datetime.fromisoformat(e['end'])>now
               and datetime.fromisoformat(e['start']).astimezone(zone).date()<=now.date()
               and datetime.fromisoformat(e['end']).astimezone(zone).date()>=now.date()]
        return prefix+(f'You have {len(items)} ongoing or upcoming events today. '+_list(items,lambda e:_event(e,zone,now.date()))
                       if items else 'No ongoing or upcoming events remain today on your selected calendars.')
    if intent=='ongoing':
        items=[e for e in events if not e['all_day'] and datetime.fromisoformat(e['start'])<=now<datetime.fromisoformat(e['end'])]
        return prefix+('Happening now: '+_list(items,lambda e:_event(e,zone,now.date())) if items else 'No timed event is happening now.')
    day=now.date()+timedelta(days=int(intent=='calendar_tomorrow'))
    items=[e for e in events if datetime.fromisoformat(e['start']).astimezone(zone).date()<=day and datetime.fromisoformat(e['end']).astimezone(zone)>datetime.combine(day,datetime.min.time(),zone)]
    label='Tomorrow' if intent=='calendar_tomorrow' else 'Today'
    return prefix+(f'{label} has {len(items)} events. '+_list(items,lambda e:_event(e,zone,day)) if items else f'{label} has no events on your selected calendars.')

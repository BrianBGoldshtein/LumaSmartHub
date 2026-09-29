"""Small deterministic spoken answers. No model, network, or paid service calls."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import math
import re


QUERY_PHRASES = {
    'next_departure': ('when is my next departure', 'when is the next departure', 'what is my next departure', 'next departure'),
    'weather_today': ('what is the weather today', "what's the weather today", 'what is the forecast today', 'how is the weather today'),
    'weather_now': ('what is the weather', "what's the weather", 'what is the temperature', 'how hot is it', 'how cold is it', 'what is the weather right now'),
    'rain_today': ('will it rain today', 'is it going to rain today', 'do i need an umbrella'),
    'next_event': ('when is my next event', 'what is my next event', "what's my next event", 'what is next on my calendar', 'when is my next appointment'),
    'calendar_today': ('what is on my calendar today', "what's on my calendar today", 'what is my schedule today', 'what do i have today', 'read my calendar today'),
    'calendar_tomorrow': ('what is on my calendar tomorrow', "what's on my calendar tomorrow", 'what is my schedule tomorrow', 'what do i have tomorrow'),
    'ongoing': ('what is happening now', 'what event is happening now', 'am i in an event right now'),
    'tasks_today': ('what are my tasks today', 'what is on my to do list', "what's on my to do list", 'read my tasks'),
    'tasks_due': ('what tasks are due today', 'what is due today'),
    'time': ('what time is it', 'tell me the time'),
    'date': ('what day is it', 'what is the date today', "what's the date today"),
    'timer_status': ('how much time is left', 'how much time is left on my timer', 'what is my timer status'),
    'help': ('what can you do', 'what can i say', 'help', 'voice commands'),
}

LIBRARY = [
    {'title':'Transit', 'examples':['Show transit', 'When is my next departure?']},
    {'title':'Weather', 'examples':['What’s the weather today?', 'Will it rain today?', 'What is the temperature?']},
    {'title':'Calendar', 'examples':['When is my next event?', 'What’s on my calendar today?', 'What’s on my calendar tomorrow?', 'What is happening now?']},
    {'title':'Tasks & time', 'examples':['What are my tasks today?', 'What tasks are due today?', 'What time is it?', 'What day is it?', 'How much time is left on my timer?']},
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
    return ALIASES.get(normalize(text))


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


def answer_query(intent, snapshot):
    if intent not in QUERY_PHRASES:
        return 'That question is not in my local library. Say, Hey Luma, what can I say?'
    if intent=='help':
        return 'Try: What is the weather today? When is my next event? What is on my calendar today? What are my tasks today? Start focus timer, or run a configured Morning, Night, Arrival or Away scene. Find more phrases in Hey Luma setup. I answer locally, without an AI service.'
    if (snapshot.get('display') or {}).get('awaiting_clock'):
        return 'My clock is still syncing. Please try again once the time is set.'
    zone=ZoneInfo(snapshot['settings']['timezone'])
    now=datetime.fromisoformat(snapshot['server_time']).astimezone(zone)
    if intent=='time': return f"It is {_time(now)}."
    if intent=='date': return f"Today is {now.strftime('%A, %B')} {now.day}, {now.year}."
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
    if intent.startswith('weather') or intent=='rain_today':
        weather=snapshot.get('weather')
        if not weather: return 'I do not have a saved forecast yet. Set your location and connect to the internet in setup.'
        observed=datetime.fromisoformat(weather['observed_at']).astimezone(zone)
        old=weather['stale'] or observed.date()!=now.date()
        prefix=f"My last saved forecast is from {observed.strftime('%B')} {observed.day} at {_time(observed)}; it may be out of date. " if old else ''
        if intent=='rain_today':
            hours=[h for h in weather.get('hourly',[]) if datetime.fromisoformat(h['time']).astimezone(zone).date()==now.date() and datetime.fromisoformat(h['time'])>=now]
            chances=[h['precipitation_probability'] for h in hours if h.get('precipitation_probability') is not None]
            if not chances: return prefix+'I do not have precipitation probabilities for the rest of today.'
            return prefix+f"The highest hourly chance of precipitation in the remaining saved forecast today is {max(chances)} percent."+(' Some hours are missing.' if len(chances)<len(hours) else '')
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
        items=[t for t in snapshot['todos'] if not t['completed'] and (intent!='tasks_due' or t['due_date']==now.date().isoformat())]
        if not items: return prefix+('No outstanding tasks due today.' if intent=='tasks_due' else 'No outstanding tasks on today’s list.')
        return prefix+f"{len(items)} outstanding {'tasks due today' if intent=='tasks_due' else 'tasks today'}. "+_list(items,lambda t:f"{_text(t['summary'])}.")
    events=meta['events']
    if intent=='next_event':
        items=[e for e in events if datetime.fromisoformat(e['start'])>now]
        return prefix+('Your next event is '+_event(items[0],zone,now.date()) if items else 'No upcoming event in the saved week ahead.')
    if intent=='ongoing':
        items=[e for e in events if not e['all_day'] and datetime.fromisoformat(e['start'])<=now<datetime.fromisoformat(e['end'])]
        return prefix+('Happening now: '+_list(items,lambda e:_event(e,zone,now.date())) if items else 'No timed event is happening now.')
    day=now.date()+timedelta(days=int(intent=='calendar_tomorrow'))
    items=[e for e in events if datetime.fromisoformat(e['start']).astimezone(zone).date()<=day and datetime.fromisoformat(e['end']).astimezone(zone)>datetime.combine(day,datetime.min.time(),zone)]
    label='Tomorrow' if intent=='calendar_tomorrow' else 'Today'
    return prefix+(f'{label} has {len(items)} events. '+_list(items,lambda e:_event(e,zone,day)) if items else f'{label} has no events on your selected calendars.')

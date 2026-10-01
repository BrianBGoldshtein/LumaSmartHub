from __future__ import annotations

import re

from .models import Command, CommandName, Page, Theme
from .voice_library import QUERY_PHRASES, query_intent
from .voice_model import match


NUMBER_WORDS = {
    "zero": 0, "ten": 10, "twenty": 20, "thirty": 30, "forty": 40,
    "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
    "one hundred": 100,
}

TIMER_MINUTES = {'five':5, 'ten':10, 'fifteen':15, 'twenty':20, 'twenty five':25,
                 'thirty':30, 'forty five':45, 'sixty':60}

SMALL_NUMBERS = {'one':1,'two':2,'three':3,'four':4,'five':5,'six':6,'seven':7,
                 'eight':8,'nine':9,'ten':10,'eleven':11,'twelve':12,
                 'thirteen':13,'fourteen':14,'fifteen':15,'sixteen':16,
                 'seventeen':17,'eighteen':18,'nineteen':19}
TENS = {'twenty':20,'thirty':30,'forty':40,'fifty':50,'sixty':60,
        'seventy':70,'eighty':80,'ninety':90}


def _spoken_number(value: str) -> int | None:
    value=value.strip().replace('-',' ')
    if value.isascii() and value.isdigit():return int(value)
    if value in SMALL_NUMBERS:return SMALL_NUMBERS[value]
    if value in TENS:return TENS[value]
    words=value.split()
    if len(words)==2 and words[0] in TENS and words[1] in SMALL_NUMBERS and SMALL_NUMBERS[words[1]]<10:
        return TENS[words[0]]+SMALL_NUMBERS[words[1]]
    if words and words[0] in {'a','one','two'} and len(words)>1 and words[1]=='hundred':
        base=(1 if words[0]=='a' else SMALL_NUMBERS[words[0]])*100
        remainder=_spoken_number(' '.join(words[2:])) if len(words)>2 else 0
        return base+remainder if remainder is not None else None
    return None


def command_grammar(wake_phrase: str = "hey luma") -> list[str]:
    """Constrain the small offline model to supported device commands, not dictation."""
    commands = [
        "good morning", "good night", "screen off", "turn off the screen", "turn the screen off", "wake screen", "privacy", "hide my calendar",
        "show weather", "show forecast", "show calendar", "show agenda",
        "show tasks", "show home screen", "show ambient", "show countdowns", "show dates", "show transit", "next page", "previous page",
        "change brightness", "make it brighter", "dim the screen", "change volume", "change theme to glass",
        "change theme to hearth", "change theme to arcade",
        "start focus timer", "start break timer", "pause timer", "resume timer", "cancel timer", "show timer", "dismiss timer",
        "run morning scene", "run night scene", "run arrival scene", "run away scene", "cancel scene",
    ]
    commands += [f"set {control} to {number}" for control in ("brightness", "volume") for number in NUMBER_WORDS]
    commands += [f"start a {number} minute timer" for number in TIMER_MINUTES]
    commands += [phrase for phrases in QUERY_PHRASES.values() for phrase in phrases]
    return ["[unk]", wake_phrase, *commands, *(f"{wake_phrase} {command}" for command in commands)]


def _percentage(text: str) -> int | None:
    match = re.search(r"\b(100|[1-9]?\d)\b", text)
    if match:
        return int(match.group(1))
    return next((value for word, value in sorted(NUMBER_WORDS.items(), key=lambda item: -len(item[0])) if re.search(r"\b"+word+r"\b", text)), None)


class WakeGate:
    """A recognizer-based command window; never used as proof of identity."""
    def __init__(self, phrase: str = "hey luma", window_seconds: float = 7):
        self.phrase = phrase.casefold().strip()
        self.window_seconds = window_seconds
        self.until = 0.0

    def accept(self, transcript: str, now: float) -> str | None:
        text = re.sub(r"\s+", " ", transcript.casefold().strip())
        match = re.search(r"\b" + re.escape(self.phrase) + r"\b", text)
        if match:
            self.until = now + self.window_seconds
            text = text[match.end():].strip(" ,.")
            if not text:
                return ""
        elif now >= self.until:
            return None
        if not text:
            return None
        self.until = 0
        return text


def parse_local_command(transcript: str) -> Command | None:
    text = re.sub(r"\s+", " ", transcript.strip().casefold())
    text = re.sub(r"^(hey\s+)?luma[,.]?\s*", "", text)
    if not text:
        return None
    # A keyword must never override an explicit negation. In particular,
    # "don't set brightness to zero" must not become a SET_BRIGHTNESS action.
    if re.search(r"\b(?:don't|dont|do not|never|not)\b", text):
        return None
    scene_phrases = {
        "run morning scene": "morning", "run night scene": "night",
        "run arrival scene": "arrive", "run away scene": "away",
    }
    if text in scene_phrases:
        return Command(CommandName.RUN_SCENE, scene_phrases[text], "voice")
    if text == "cancel scene":
        return Command(CommandName.CANCEL_SCENE, source="voice")
    if intent := query_intent(text):
        return Command(CommandName.LOCAL_QUERY, intent, 'voice')
    # Unsupported questions must not fall through keyword matching into a
    # navigation/mutation command, or ever reach the optional cloud adapter.
    if re.match(r"^(?:what|what's|when|where|why|how|will|is|are|do|does|can|could|would|ask|question|tell me|explain|describe)\b", text):
        return None
    if text in {'screen off','turn screen off','turn off the screen','turn the screen off'}:
        return Command(CommandName.SCREEN_OFF, source='voice')
    if text in {'wake screen','wake up screen'}:
        return Command(CommandName.WAKE, source='voice')
    if text in {'start focus timer', 'start break timer'}:
        return Command(CommandName.START_TIMER, 'focus' if 'focus' in text else 'break', 'voice')
    if text in {'pause timer','resume timer','cancel timer','show timer','dismiss timer'}:
        return Command(CommandName(text.replace(' ', '_')), source='voice')
    timer_match = re.fullmatch(r'(?:start|set)(?: a)? (.+?)(?:-| )(minute|minutes|hour|hours) timer', text)
    if timer_match:
        amount=_spoken_number(timer_match[1])
        minutes=amount*(60 if timer_match[2].startswith('hour') else 1) if amount is not None else None
        return Command(CommandName.START_TIMER, minutes, 'voice') if minutes is not None and 1<=minutes<=120 else None
    timer_match = re.fullmatch(r'(?:start|set)(?: a)? timer (?:for|of) (.+?) (minute|minutes|hour|hours)', text)
    if timer_match:
        amount=_spoken_number(timer_match[1])
        minutes=amount*(60 if timer_match[2].startswith('hour') else 1) if amount is not None else None
        return Command(CommandName.START_TIMER, minutes, 'voice') if minutes is not None and 1<=minutes<=120 else None
    if "good morning" in text:
        return Command(CommandName.GOOD_MORNING, source="voice")
    if "good night" in text:
        return Command(CommandName.GOOD_NIGHT, source="voice")
    if any(phrase in text for phrase in ("privacy", "hide my", "hide private")):
        return Command(CommandName.PRIVACY_NOW, source="voice")
    if "brightness" in text or "screen brighter" in text or "screen dimmer" in text or text in {'make it brighter','dim the screen'}:
        value = _percentage(text)
        return Command(CommandName.SET_BRIGHTNESS if value is not None else CommandName.SHOW_BRIGHTNESS, value, "voice")
    if "volume" in text or "louder" in text or "quieter" in text:
        value = _percentage(text)
        return Command(CommandName.SET_VOLUME if value is not None else CommandName.SHOW_VOLUME, value, "voice")
    if "theme" in text or "look" in text:
        if any(word in text for word in ("hearth", "cabin", "wood")):
            return Command(CommandName.SET_THEME, Theme.HEARTH, "voice")
        if any(word in text for word in ("neon", "arcade", "grid")):
            return Command(CommandName.SET_THEME, Theme.NEON_GRID, "voice")
        if any(word in text for word in ("glass", "default", "clean")):
            return Command(CommandName.SET_THEME, Theme.LUMA_GLASS, "voice")
    page_phrases = {
        Page.TRANSIT: ('show transit',),
        Page.COUNTDOWNS: ('countdowns','show dates'),
        Page.WEATHER: ("weather", "forecast"), Page.AGENDA: ("agenda", "calendar", "schedule"),
        Page.TODOS: ("to-do", "todo", "tasks"), Page.HOME: ("home screen", "at a glance"),
        Page.AMBIENT: ("ambient", "quiet screen"),
    }
    for page, phrases in page_phrases.items():
        if any(phrase in text for phrase in phrases):
            return Command(CommandName.SHOW_PAGE, page, "voice")
    if "next" in text:
        return Command(CommandName.NEXT_PAGE, source="voice")
    if "previous" in text or "go back" in text:
        return Command(CommandName.PREVIOUS_PAGE, source="voice")
    # The neural matcher may only select reversible local presentation actions.
    # It never supplies numeric slots, calendar writes, scenes or a privacy key.
    action=match(text,confidence=.78,margin=1.8)
    actions={
        'action:home':(CommandName.SHOW_PAGE,Page.HOME),
        'action:weather':(CommandName.SHOW_PAGE,Page.WEATHER),
        'action:agenda':(CommandName.SHOW_PAGE,Page.AGENDA),
        'action:todos':(CommandName.SHOW_PAGE,Page.TODOS),
        'action:ambient':(CommandName.SHOW_PAGE,Page.AMBIENT),
        'action:countdowns':(CommandName.SHOW_PAGE,Page.COUNTDOWNS),
        'action:transit':(CommandName.SHOW_PAGE,Page.TRANSIT),
        'action:next_page':(CommandName.NEXT_PAGE,None),
        'action:previous_page':(CommandName.PREVIOUS_PAGE,None),
        'action:brightness':(CommandName.SHOW_BRIGHTNESS,None),
        'action:volume':(CommandName.SHOW_VOLUME,None),
        'action:glass':(CommandName.SET_THEME,Theme.LUMA_GLASS),
        'action:hearth':(CommandName.SET_THEME,Theme.HEARTH),
        'action:arcade':(CommandName.SET_THEME,Theme.NEON_GRID),
    }
    if action in actions:
        name,value=actions[action]
        return Command(name,value,'voice')
    return None

from datetime import datetime
from zoneinfo import ZoneInfo


def morning_briefing(snapshot: dict) -> str:
    """Consume only the privacy-filtered snapshot, never raw calendar storage."""
    if (snapshot.get('display') or {}).get('awaiting_clock'):
        return 'Good morning. My clock is still syncing; private details stay hidden.'
    now = datetime.fromisoformat(snapshot["server_time"]).astimezone(ZoneInfo(snapshot["settings"]["timezone"]))
    parts = [f"Good morning. It's {now.strftime('%A, %B')} {now.day}, {now.strftime('%I:%M %p').lstrip('0')}."]
    weather = snapshot.get("weather")
    if weather:
        prefix = "The last saved forecast says" if weather["stale"] else "It's"
        parts.append(f"{prefix} {round(weather['temperature'])} degrees, with a high of {round(weather['high'])} and a low of {round(weather['low'])}.")
    if snapshot["privacy_redacted"]:
        parts.append("Your calendar is private. Connect your phone or unlock with your PIN to hear your plans.")
    else:
        events = snapshot.get("calendar", [])[:3]
        if not events:
            parts.append("No upcoming events on your selected calendars.")
        for event in events:
            time = datetime.fromisoformat(event["start"]).astimezone(now.tzinfo)
            when = "all day" if event["all_day"] else time.strftime("%I:%M %p").lstrip("0")
            if time.date() != now.date():
                when += f" on {time.strftime('%A')}"
            parts.append(f"{event['summary'][:160]}, {when}.")
    return " ".join(parts)

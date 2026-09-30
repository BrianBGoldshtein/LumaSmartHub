from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Callable

from .models import (
    Command,
    CommandName,
    CommandResult,
    Orientation,
    Page,
    Settings,
    Theme,
)
from .state_machine import StateMachine
from .storage import Storage


class CommandRouter:
    def __init__(
        self,
        storage: Storage,
        state_machine: StateMachine,
        *,
        cloud_ask: Callable[[str], str] | None = None,
    ):
        self.storage = storage
        self.state_machine = state_machine
        self.cloud_ask = cloud_ask

    @property
    def settings(self) -> Settings:
        return self.state_machine.settings

    def _save(self) -> None:
        self.storage.save_settings(self.settings)

    def execute(self, command: Command, now: datetime | None = None) -> CommandResult:
        now = now or datetime.now(UTC)
        name = command.name

        if name == CommandName.SET_BRIGHTNESS:
            value = _percentage(command.value, "brightness")
            self.settings.brightness = value
            self._save()
            return CommandResult(True, f"Brightness set to {value} percent.", True)

        if name == CommandName.SHOW_BRIGHTNESS:
            return CommandResult(True, "Brightness control opened.", data={"overlay": "brightness"})

        if name == CommandName.SET_VOLUME:
            value = _percentage(command.value, "volume")
            self.settings.volume = value
            self._save()
            return CommandResult(True, f"Volume set to {value} percent.", True)

        if name == CommandName.SHOW_VOLUME:
            return CommandResult(True, "Volume control opened.", data={"overlay": "volume"})

        if name == CommandName.SET_THEME:
            self.settings.theme = Theme(str(command.value))
            self._save()
            return CommandResult(True, f"Theme changed to {self.settings.theme.value}.", True)

        if name == CommandName.SET_ORIENTATION:
            self.settings.orientation = Orientation(str(command.value))
            self._save()
            return CommandResult(True, "Orientation updated.", True)

        if name == CommandName.SHOW_PAGE:
            page = Page(str(command.value))
            self.state_machine.state.active_page = page
            return CommandResult(True, f"Showing {page.value}.", True)

        if name == CommandName.PAUSE_CYCLE:
            self.state_machine.state.cycle_paused_until = now + timedelta(minutes=2)
            return CommandResult(True, "Screen rotation paused for two minutes.", True)

        if name == CommandName.RESUME_CYCLE:
            self.state_machine.state.cycle_paused_until = None
            return CommandResult(True, "Screen rotation resumed.", True)

        if name == CommandName.PRIVACY_NOW:
            self.state_machine.force_private(now)
            return CommandResult(True, "Private information is hidden.", True)

        if name == CommandName.GOOD_NIGHT:
            self.state_machine.good_night(now)
            return CommandResult(True, "Good night. I will keep the room dark.", True)

        if name == CommandName.SCREEN_OFF:
            return CommandResult(True, 'Screen off. Touch or say wake screen to resume.', True)

        if name == CommandName.GOOD_MORNING:
            self.state_machine.good_morning(now)
            return CommandResult(True, "Good morning.", True, {"briefing": True})

        if name == CommandName.WAKE:
            self.state_machine.temporary_wake(now)
            return CommandResult(True, "Screen awake for five minutes.", True)

        if name in (CommandName.NEXT_PAGE, CommandName.PREVIOUS_PAGE):
            pages = list(Page)
            current = pages.index(self.state_machine.state.active_page)
            offset = 1 if name == CommandName.NEXT_PAGE else -1
            self.state_machine.state.active_page = pages[(current + offset) % len(pages)]
            return CommandResult(
                True,
                f"Showing {self.state_machine.state.active_page.value}.",
                True,
            )

        if name == CommandName.ASK:
            question = str(command.value or "").strip()
            if not question:
                return CommandResult(False, "A question is required.")
            if self.settings.cloud_provider == "disabled" or self.cloud_ask is None:
                return CommandResult(False, "Cloud questions are not configured.")
            return CommandResult(True, self.cloud_ask(question), data={"cloud": True})

        return CommandResult(False, f"Unsupported command: {name.value}")


def _percentage(value: object, label: str) -> int:
    try:
        percentage = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be a whole-number percentage") from exc
    if not 0 <= percentage <= 100:
        raise ValueError(f"{label} must be between 0 and 100")
    return percentage

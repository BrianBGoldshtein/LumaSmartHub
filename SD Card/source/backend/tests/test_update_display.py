from datetime import UTC,datetime,timedelta
import pytest
from luma.service import LumaService
from luma.storage import Storage
from luma.models import CalendarEvent

@pytest.mark.parametrize('night_clock',[False,True])
@pytest.mark.parametrize('pending',[False,True])
def test_update_display_is_visible_but_sleep_settings_and_private_data_survive(tmp_path,night_clock,pending):
    now=datetime(2026,10,8,23,tzinfo=UTC)
    storage=Storage(tmp_path/'luma.db');settings=storage.load_settings()
    settings.onboarding_completed=True;settings.night_clock_enabled=night_clock
    settings.sleep_calendar_ids=['sleep'];settings.visible_calendar_ids=['events']
    settings.brightness=0;settings.timezone='UTC';storage.save_settings(settings)
    service=LumaService(storage);service.display_clock_trusted=lambda:True
    service.replace_events([CalendarEvent('sleep','sleep','Sleep',now-timedelta(hours=1),now+timedelta(hours=6)),
                            CalendarEvent('private','events','PRIVATE',now,now+timedelta(hours=1))],now)
    service.phone_seen(now)
    prior=service.snapshot(now)
    assert prior['display']['mode'] in {'night-clock','off'}
    before=storage.get_cache('display','cycle')
    service.presence_update_pending=int(pending);service.presence_update_busy=not pending
    installing=service.snapshot(now)
    assert installing['display']['mode']=='day' and installing['state']['display_power']=='on'
    assert installing['display']['brightness']==20
    assert installing['privacy_redacted'] and not installing['calendar'] and not installing['user_panels']
    assert storage.get_cache('display','cycle')==before
    assert storage.load_settings()==settings
    service.presence_update_pending=0;service.presence_update_busy=False
    restored=service.snapshot(now)
    assert restored['display']['mode']==prior['display']['mode']
    assert storage.load_settings()==settings

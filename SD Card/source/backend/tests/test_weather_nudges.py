from copy import deepcopy
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from unittest.mock import Mock

import httpx
import pytest
from fastapi.testclient import TestClient

from luma.api import create_app
from luma.integrations.open_meteo import OpenMeteoClient, parse_forecast
from luma.models import Settings, WeatherHour, WeatherSnapshot
from luma.serde import to_primitive, weather_from_dict
from luma.service import LumaService
from luma.storage import Storage
from luma.weather_nudges import weather_nudge

NOW = datetime(2026, 9, 26, 12, tzinfo=UTC)


def forecast(**hour):
    return WeatherSnapshot(NOW, 68, 68, 75, 55, 1, 'Mostly clear.', hourly=[
        WeatherHour(**({'time':NOW+timedelta(hours=1),'temperature':68,'precipitation_probability':0,'weather_code':61} | hour))])


def hint(weather, now=NOW, **preferences):
    return weather_nudge(weather, Settings(weather_nudges_enabled=True, **preferences), now)


@pytest.mark.parametrize('hour,kind', [
    ({'precipitation_probability':50,'wind_gust_mph':30,'apparent_temperature':95}, 'precipitation'),
    ({'precipitation_probability':49,'wind_gust_mph':25,'apparent_temperature':95}, 'wind'),
    ({'wind_gust_mph':24.9,'apparent_temperature':90}, 'heat'),
    ({'apparent_temperature':45}, 'cold'),
])
def test_inclusive_thresholds_and_priority(hour,kind):
    assert hint(forecast(**hour))['kind']==kind


@pytest.mark.parametrize('code,title', [(61,'Rain possible'), (73,'Snow possible'), (66,'Wintry weather'), (1,'Wet weather possible')])
def test_precipitation_not_always_rain(code,title):
    assert hint(forecast(precipitation_probability=60,weather_code=code))['title']==title


def test_configurable_thresholds_and_disablement():
    weather=forecast(precipitation_probability=60,wind_gust_mph=28,apparent_temperature=94)
    assert hint(weather, weather_rain_percent=70)['kind']=='wind'
    assert hint(weather, weather_rain_percent=70,weather_gust_mph=30)['kind']=='heat'
    assert hint(weather, weather_rain_percent=70,weather_gust_mph=30,weather_hot_f=95) is None
    assert weather_nudge(weather, Settings(), NOW) is None


@pytest.mark.parametrize('offset,expected', [(0,False),(1,True),(21600,True),(21601,False),(-3600,False)])
def test_only_next_six_hours(offset,expected):
    weather=forecast(time=NOW+timedelta(seconds=offset),precipitation_probability=50)
    assert bool(hint(weather)) is expected


def test_stale_future_and_missing_are_not_clear_weather():
    weather=forecast(precipitation_probability=70)
    assert hint(weather, NOW+timedelta(hours=2,seconds=1)) is None
    assert hint(replace(weather, observed_at=NOW-timedelta(hours=2))) is not None
    assert hint(replace(weather, observed_at=NOW+timedelta(seconds=1))) is None
    assert hint(replace(weather, stale=True)) is None
    assert hint(None) is None
    assert hint(forecast(precipitation_probability=None)) is None
    assert hint(forecast(precipitation_probability=200, wind_gust_mph=float('nan'), apparent_temperature=float('inf'))) is None
    # Ignore one missing metric without discarding another valid one.
    assert hint(forecast(precipitation_probability=None,wind_gust_mph=30))['kind']=='wind'


def payload():
    return {'current':{'time':NOW.timestamp(),'temperature_2m':68,'apparent_temperature':67,'weather_code':1},
            'daily':{'temperature_2m_max':[75], 'temperature_2m_min':[55]},
            'hourly':{'time':[NOW.timestamp()+3600,NOW.timestamp()+7200], 'temperature_2m':[67,66], 'weather_code':[61,61],
                      'precipitation_probability':[None,70], 'wind_gusts_10m':[26,None],
                      'apparent_temperature':[65,64], 'precipitation':[0,2.5]}}


def test_provider_fetches_all_metrics_in_one_request_with_explicit_units():
    requests=[]
    def respond(request):
        requests.append(request)
        return httpx.Response(200,json=payload())
    client=OpenMeteoClient(httpx.Client(transport=httpx.MockTransport(respond)))
    weather=client.fetch(latitude=37,longitude=-122,timezone='America/Los_Angeles')
    assert len(requests)==1
    query=requests[0].url.params
    assert query['timeformat']=='unixtime' and query['wind_speed_unit']=='mph' and query['precipitation_unit']=='mm'
    assert {'apparent_temperature','wind_gusts_10m','precipitation'} <= set(query['hourly'].split(','))
    assert weather.hourly[0].precipitation_probability is None
    assert weather.hourly[0].wind_gust_mph==26
    assert weather.hourly[1].precipitation_mm==2.5
    assert weather_from_dict(to_primitive(weather))==weather


@pytest.mark.parametrize('invalid',[None,[],[None,'bad'],[float('nan'),float('inf')],[-1,301],True])
def test_optional_arrays_are_missing_not_zero(invalid):
    data=payload()
    for field in ('precipitation_probability','wind_gusts_10m','precipitation'):
        data['hourly'][field]=invalid
    weather=parse_forecast(data,'UTC')
    assert weather.hourly[0].precipitation_probability is None
    assert weather.hourly[0].wind_gust_mph is None
    assert weather.hourly[0].precipitation_mm is None
    del data['hourly']['apparent_temperature']
    assert parse_forecast(data,'UTC').hourly[0].apparent_temperature is None


def test_unix_times_keep_both_fall_back_hours_and_absolute_window():
    data=payload()
    before=datetime(2026,11,1,7,30,tzinfo=UTC)
    data['current']['time']=before.timestamp()
    data['hourly']['time']=[datetime(2026,11,1,8,tzinfo=UTC).timestamp(),datetime(2026,11,1,9,tzinfo=UTC).timestamp()]
    weather=parse_forecast(data,'America/Los_Angeles')
    assert [h.time.hour for h in weather.hourly]==[1,1]
    assert [h.time.fold for h in weather.hourly]==[0,1]
    assert weather.hourly[1].time.timestamp()-weather.hourly[0].time.timestamp()==3600
    assert hint(weather, before)['kind']=='precipitation'


def test_old_cache_works_and_hint_is_public_without_extra_storage_writes(tmp_path):
    storage=Storage(tmp_path/'luma.db')
    service=LumaService(storage)
    old=to_primitive(forecast(precipitation_probability=60))
    for field in ('apparent_temperature','wind_gust_mph','precipitation_mm'):
        old['hourly'][0].pop(field)
    service.replace_weather(weather_from_dict(old))
    service.update_settings({'weather_nudges_enabled':True},now=NOW)
    service.snapshot(NOW)
    original=deepcopy(to_primitive(service.weather))
    storage.set_cache=Mock(wraps=storage.set_cache)
    for _ in range(10):
        snapshot=service.snapshot(NOW)
        assert snapshot['privacy_redacted']
        assert snapshot['weather']['nudge']['kind']=='precipitation'
    assert to_primitive(service.weather)==original
    storage.set_cache.assert_not_called()
    assert service.snapshot(NOW-timedelta(seconds=1))['weather']['stale']


def test_api_preferences_are_local_strict_atomic_and_preserve_other_settings(tmp_path):
    app=create_app(data_dir=tmp_path)
    client=TestClient(app)
    client.patch('/api/v1/settings',json={'voice_enabled':False,'timer_focus_minutes':40})
    patch={'weather_nudges_enabled':True,'weather_rain_percent':65,'weather_hot_f':99,'weather_cold_f':35}
    assert client.patch('/api/v1/settings',json=patch).status_code==200
    for invalid in ({'weather_nudges_enabled':'yes'},{'weather_rain_percent':True},{'weather_gust_mph':4},
                    {'weather_hot_f':34,'weather_rain_percent':20},{'weather_cold_f':None},{'weather_rain_percent':1.5}):
        assert client.patch('/api/v1/settings',json=invalid).status_code==422
    token=client.get('/api/v1/security/lan-token').json()['token']
    remote=TestClient(app,client=('192.0.2.1',5000))
    assert remote.patch('/api/v1/settings',headers={'X-Luma-Token':token},json=patch).status_code==403
    restored=create_app(data_dir=tmp_path).state.luma.settings
    assert restored.weather_rain_percent==65 and restored.weather_hot_f==99
    assert restored.voice_enabled is False and restored.timer_focus_minutes==40

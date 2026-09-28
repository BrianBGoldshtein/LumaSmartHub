from datetime import UTC,datetime,timedelta

from luma.models import Page,CommandName
from luma.voice import command_grammar,parse_local_command
from luma.voice_library import answer_query

NOW=datetime(2026,9,26,20,tzinfo=UTC)


def snapshot(private=False):
    row={'route':'Local','direction':'N','destination':'City','kind':'predicted','stale':False,'at':(NOW+timedelta(minutes=5)).isoformat()}
    return {'settings':{'timezone':'UTC'},'server_time':NOW.isoformat(),'privacy_redacted':private,
            'transit':[{'title':'Private commute','public':False,'departures':[row]},
                       {'title':'Public station','public':True,'departures':[{**row,'kind':'scheduled','at':(NOW+timedelta(minutes=8)).isoformat()}]}]}


def test_transit_controls_and_query_are_local_and_grammar_listed():
    assert 'show transit' in command_grammar()
    assert parse_local_command('Hey Luma, show transit').value==Page.TRANSIT
    command=parse_local_command('Hey Luma, next departure')
    assert command.name==CommandName.LOCAL_QUERY and command.value=='next_departure'


def test_next_visible_departure_honors_privacy_without_google_or_network():
    assert 'Private commute, in 5 minutes' in answer_query('next_departure',snapshot())
    reply=answer_query('next_departure',snapshot(True))
    assert 'Private commute' not in reply and 'Public station, in 8 minutes' in reply and reply.startswith('Scheduled:')


def test_stale_or_expired_departure_is_never_spoken_as_live():
    data=snapshot();data['transit'][0]['departures'][0]['stale']=True
    assert 'saved prediction' in answer_query('next_departure',data)
    for stop in data['transit']:stop['departures'][0]['at']=(NOW-timedelta(minutes=1)).isoformat()
    assert 'No departure times' in answer_query('next_departure',data)

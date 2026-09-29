from contextlib import contextmanager
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from uuid import uuid4
import asyncio

import pytest

from luma.scenes import Scenes, SCENES, definition
from luma.scene_triggers import PresenceTriggers, CalendarTriggers, SceneTrigger
from luma.scene_executor import SceneExecutor, SceneStopped
from luma.storage import Storage

NOW = datetime(2026, 9, 27, 12, tzinfo=UTC)
ACTION = {'device': 'purifier', 'action': 'power', 'value': False, 'binding': 'a' * 64}
CONFIG = {'enabled': True, 'automatic': True, 'actions': [ACTION]}


def store(tmp_path):
    return Scenes(Storage(tmp_path / 'scenes.db'))


def setup(saved, key='morning', config=None):
    saved.edit(key, deepcopy(config or CONFIG), revision=saved.revision)
    return saved


def claim(saved, key='morning', source='manual', now=NOW, occurrence=None, **kwargs):
    return saved.claim(key, source, occurrence or str(uuid4()), revision=saved.revision,
                       now=now, observed_at=kwargs.get('observed_at', now), trusted=kwargs.get('trusted', True),
                       remote_authorized=kwargs.get('remote_authorized', False))


def test_all_four_scenes_start_empty_disabled_and_without_remote_permission(tmp_path):
    saved = store(tmp_path)
    assert tuple(saved.definitions) == SCENES
    assert all(row == {'enabled': False, 'automatic': False, 'actions': []} for row in saved.definitions.values())
    assert saved.configuration()['remote_control'] is False
    for key in SCENES:
        with pytest.raises(ValueError, match='disabled'): claim(saved, key)
    assert saved.runs == []


@pytest.mark.parametrize('config', [
    {'enabled': True, 'automatic': False, 'actions': []},
    {'enabled': False, 'automatic': True, 'actions': [ACTION]},
    {**CONFIG, 'enabled': 1}, {**CONFIG, 'automatic': 'yes'},
    {**CONFIG, 'secret': 'NO'}, {**CONFIG, 'actions': [ACTION] * 9},
    {**CONFIG, 'actions': [ACTION, ACTION]},
    {**CONFIG, 'actions': [{**ACTION, 'binding': 'short'}]},
    {**CONFIG, 'actions': [{**ACTION, 'device': 'arbitrary'}]},
    {**CONFIG, 'actions': [{**ACTION, 'action': 'filter_reset'}]},
    {**CONFIG, 'actions': [{**ACTION, 'value': 1}]},
    {**CONFIG, 'actions': [{**ACTION, 'device': 'fan_1', 'action': 'power_toggle', 'value': None}]},
    {**CONFIG, 'actions': [{**ACTION, 'device': 'fan_1', 'action': 'speed_up', 'value': None}]},
    {**CONFIG, 'actions': [ACTION, {**ACTION, 'action': 'speed', 'value': 2}]},
    {**CONFIG, 'actions': [ACTION, {**ACTION, 'action': 'display', 'binding': 'b' * 64}]},
])
def test_bad_or_contradictory_actions_rejected_without_mutation(tmp_path, config):
    saved = store(tmp_path)
    before = saved.configuration()
    with pytest.raises(ValueError): saved.edit('morning', config, revision=saved.revision)
    assert saved.configuration() == before
    assert saved.storage.get_cache('room', 'scenes') is None


def test_save_reload_absolute_actions_and_independent_trigger_optin(tmp_path):
    saved = setup(store(tmp_path), config={**CONFIG, 'automatic': False})
    restored = Scenes(saved.storage)
    assert restored.definitions == saved.definitions and restored.revision == saved.revision
    assert restored.generation != saved.generation and restored.active is None
    with pytest.raises(ValueError, match='trigger'): claim(restored, source='calendar')
    assert claim(restored)['source'] == 'manual'
    value = {'enabled': True, 'automatic': False, 'actions': [
        {**ACTION, 'device': 'fan_1', 'action': 'power_off', 'value': None},
        {**ACTION, 'device': 'fan_2', 'action': 'speed_2', 'value': None},
    ]}
    assert definition(value) == value


@pytest.mark.parametrize('source', ['presence', 'pin', 'tailscale', 'boot', 'token_refresh'])
def test_unrecognized_or_wrong_scene_trigger_cannot_claim(tmp_path, source):
    saved = setup(store(tmp_path))
    with pytest.raises(ValueError, match='trigger'): claim(saved, source=source)
    assert saved.runs == []


def test_remote_claim_requires_internal_explicit_permission_and_is_journaled(tmp_path):
    saved=setup(store(tmp_path),config={**CONFIG,'automatic':False})
    with pytest.raises(ValueError,match='allowlisted'):
        claim(saved,source='remote')
    run=claim(saved,source='remote',remote_authorized=True)
    assert run['source']=='remote'
    assert Scenes(saved.storage).configuration()['runs'][-1]['source']=='remote'


@pytest.mark.parametrize('age,trusted', [(16, True), (-1, True), (0, False), (0, 1)])
def test_stale_future_and_untrusted_triggers_cannot_run(tmp_path, age, trusted):
    saved = setup(store(tmp_path))
    with pytest.raises(ValueError): claim(saved, observed_at=NOW - timedelta(seconds=age), trusted=trusted)
    assert saved.runs == []


def test_durable_claim_step_and_result_each_precede_live_state(tmp_path, monkeypatch):
    saved = setup(store(tmp_path))
    original = saved.storage.set_cache
    writes = []
    def check_write(namespace, key, raw):
        writes.append(deepcopy(raw))
        assert saved.runs != raw['runs']
        original(namespace, key, raw)
    monkeypatch.setattr(saved.storage, 'set_cache', check_write)
    run = claim(saved)
    assert writes[-1]['runs'][-1]['steps'][0]['status'] == 'not_started'
    assert saved.begin_step(run['id'], 0, generation=saved.generation) == ACTION
    assert writes[-1]['runs'][-1]['steps'][0]['status'] == 'unknown'
    saved.finish_step(run['id'], 0, 'unconfirmed', generation=saved.generation)
    saved.finish(run['id'], generation=saved.generation)
    assert saved.runs[-1]['finished'] and saved.active is None


def test_restart_exposes_interrupted_unknown_but_cannot_resume(tmp_path):
    saved = setup(store(tmp_path))
    run = claim(saved)
    saved.begin_step(run['id'], 0, generation=saved.generation)
    restored = Scenes(saved.storage)
    view = restored.configuration()
    assert view['runs'][-1]['interrupted'] and view['runs'][-1]['steps'][0]['status'] == 'unknown'
    assert not view['busy']
    for generation in (saved.generation, restored.generation):
        with pytest.raises(ValueError, match='replayed'): restored.begin_step(run['id'], 0, generation=generation)
        with pytest.raises(ValueError, match='replayed'): restored.finish_step(run['id'], 0, 'confirmed', generation=generation)
    with pytest.raises(ValueError, match='consumed'): claim(restored, occurrence=run['id'], now=NOW + timedelta(hours=1))


def test_no_overlap_and_five_minute_cooldown_survives_restart_and_edit(tmp_path):
    saved = setup(store(tmp_path))
    run = claim(saved)
    with pytest.raises(ValueError, match='already running'): claim(saved, now=NOW + timedelta(hours=1))
    saved.finish(run['id'], generation=saved.generation)
    restored = setup(Scenes(saved.storage))
    for seconds in (-1, 0, 299):
        with pytest.raises(ValueError, match='cooling'): claim(restored, now=NOW + timedelta(seconds=seconds))
    assert claim(restored, now=NOW + timedelta(minutes=5))


def test_disabling_during_dispatch_allows_result_but_blocks_next_step(tmp_path):
    saved = setup(store(tmp_path), config={**CONFIG, 'actions': [ACTION, {**ACTION, 'action': 'display'}]})
    run = claim(saved)
    saved.begin_step(run['id'], 0, generation=saved.generation)
    saved.edit('morning', {'enabled': False, 'automatic': False, 'actions': [ACTION]}, revision=saved.revision)
    saved.finish_step(run['id'], 0, 'confirmed', generation=saved.generation)
    with pytest.raises(ValueError, match='changed'): saved.begin_step(run['id'], 1, generation=saved.generation)
    saved.finish(run['id'], generation=saved.generation)
    assert saved.runs[-1]['steps'][1]['status'] == 'not_started'


def test_step_cannot_skip_preceding_step_or_repeat_even_after_result(tmp_path):
    saved = setup(store(tmp_path), config={**CONFIG, 'actions': [ACTION, {**ACTION, 'action': 'display'}]})
    run = claim(saved)
    with pytest.raises(ValueError, match='preceding'): saved.begin_step(run['id'], 1, generation=saved.generation)
    saved.begin_step(run['id'], 0, generation=saved.generation)
    with pytest.raises(ValueError, match='replayed'): saved.begin_step(run['id'], 0, generation=saved.generation)
    saved.finish_step(run['id'], 0, 'skipped_override', generation=saved.generation)
    with pytest.raises(ValueError): saved.finish_step(run['id'], 0, 'confirmed', generation=saved.generation)
    assert saved.begin_step(run['id'], 1, generation=saved.generation)['action'] == 'display'


@pytest.mark.parametrize('phase', ['edit', 'claim', 'begin', 'result', 'finish'])
def test_disk_failure_preserves_live_and_saved_state(tmp_path, monkeypatch, phase):
    saved = setup(store(tmp_path))
    run = claim(saved) if phase in ('begin', 'result', 'finish') else None
    if phase == 'result': saved.begin_step(run['id'], 0, generation=saved.generation)
    before = saved.configuration()
    disk = saved.storage.get_cache('room', 'scenes')
    @contextmanager
    def failed(): raise OSError('disk full'); yield
    monkeypatch.setattr(saved.storage, 'transaction', failed)
    with pytest.raises(OSError):
        if phase == 'edit': setup(saved, 'night')
        elif phase == 'claim': claim(saved)
        elif phase == 'begin': saved.begin_step(run['id'], 0, generation=saved.generation)
        elif phase == 'result': saved.finish_step(run['id'], 0, 'confirmed', generation=saved.generation)
        else: saved.finish(run['id'], generation=saved.generation)
    assert saved.configuration() == before
    assert saved.storage.get_cache('room', 'scenes') == disk


@pytest.mark.parametrize('bad', [[], {}, {'version': True}, {'version': 99}])
def test_corrupt_store_never_overwritten(tmp_path, bad):
    storage = Storage(tmp_path / 'scenes.db')
    storage.set_cache('room', 'scenes', bad)
    saved = Scenes(storage)
    assert saved.recovery_error
    with pytest.raises(ValueError, match='recovery'): setup(saved)
    assert storage.get_cache('room', 'scenes') == bad


def test_history_is_bounded_and_configuration_cannot_mutate_it(tmp_path):
    saved = setup(store(tmp_path))
    for index in range(44):
        run = claim(saved, now=NOW + timedelta(minutes=5 * index))
        saved.finish(run['id'], generation=saved.generation)
    assert len(saved.runs) == 40
    view = saved.configuration()
    view['definitions']['morning']['actions'].clear()
    view['runs'].clear()
    assert saved.definitions['morning']['actions'] and len(saved.runs) == 40
    assert not Scenes(saved.storage).recovery_error


def presence(monitor, connected, seconds, identity='paired-phone', trusted=True):
    return monitor.observe(connected, identity=identity, monotonic=seconds,
                           now=NOW + timedelta(seconds=seconds), trusted=trusted)


def test_presence_boot_baseline_never_arrival_and_true_transition_debounced():
    monitor = PresenceTriggers()
    for second in range(40): assert presence(monitor, True, second) is None
    for second in range(40, 220): assert presence(monitor, False, second) is None
    event = presence(monitor, False, 220)
    assert event.scene == 'away' and event.source == 'presence'
    for second in range(221, 300): assert presence(monitor, False, second) is None
    for second in range(300, 330): assert presence(monitor, True, second) is None
    assert presence(monitor, True, 330).scene == 'arrive'
    assert presence(monitor, True, 331) is None


@pytest.mark.parametrize('reset', ['unknown', 'new_phone', 'untrusted', 'gap', 'rollback'])
def test_presence_unknown_repair_clock_or_worker_gap_does_not_replay(reset):
    monitor = PresenceTriggers()
    presence(monitor, False, 0)
    for second in range(1, 30): assert presence(monitor, True, second) is None
    if reset == 'unknown': presence(monitor, None, 30)
    elif reset == 'new_phone': presence(monitor, True, 30, identity='new-phone')
    elif reset == 'untrusted': presence(monitor, True, 30, trusted=False)
    elif reset == 'gap': presence(monitor, True, 90)
    else: presence(monitor, True, 0)
    for second in range(100, 140): assert presence(monitor, True, second) is None


def test_presence_flapping_cancels_candidate():
    monitor = PresenceTriggers()
    presence(monitor, False, 0)
    for second in range(1, 29): presence(monitor, True, second)
    assert presence(monitor, False, 29) is None
    for second in range(30, 60): assert presence(monitor, True, second) is None
    assert presence(monitor, True, 60).scene == 'arrive'


def calendar(monitor, interval, seconds, **kw):
    return monitor.observe(interval, revision=kw.get('revision', 'selection-1'), monotonic=kw.get('mono', seconds),
                           now=NOW + timedelta(seconds=seconds), trusted=kw.get('trusted', True), fresh=kw.get('fresh', True))


def test_calendar_only_crossed_boundaries_emit_not_boot_or_refresh():
    monitor = CalendarTriggers()
    interval = (NOW + timedelta(seconds=5), NOW + timedelta(seconds=12))
    assert calendar(monitor, None, 0) is None
    assert calendar(monitor, None, 4) is None
    assert calendar(monitor, interval, 5).scene == 'night'
    assert calendar(monitor, interval, 9) is None
    assert calendar(monitor, None, 12).scene == 'morning'
    assert calendar(monitor, None, 13) is None
    boot = CalendarTriggers()
    assert calendar(boot, interval, 6) is None


def test_calendar_extension_prevents_early_wake_and_deletion_is_not_morning():
    monitor = CalendarTriggers()
    original = (NOW, NOW + timedelta(seconds=10))
    extended = (NOW, NOW + timedelta(seconds=20))
    calendar(monitor, original, 0)
    calendar(monitor, original, 4)
    assert calendar(monitor, extended, 8) is None
    assert calendar(monitor, extended, 12) is None
    assert calendar(monitor, None, 16) is None  # Deletion before known boundary.


@pytest.mark.parametrize('change', ['revision', 'fresh', 'trusted', 'gap', 'wall_jump'])
def test_calendar_discontinuity_never_replays_missed_sleep_end(change):
    monitor = CalendarTriggers()
    interval = (NOW, NOW + timedelta(seconds=5))
    calendar(monitor, interval, 0)
    if change == 'revision': assert calendar(monitor, None, 5, revision='changed') is None
    elif change == 'fresh': assert calendar(monitor, None, 5, fresh=False) is None
    elif change == 'trusted': assert calendar(monitor, None, 5, trusted=False) is None
    elif change == 'gap': assert calendar(monitor, None, 10) is None
    else: assert calendar(monitor, None, 100, mono=2) is None
    assert calendar(monitor, None, 105) is None


def trigger(): return SceneTrigger('morning', 'manual', str(uuid4()), NOW)


def executor(saved, dispatch, **kwargs):
    return SceneExecutor(saved, dispatch=dispatch, authorize=kwargs.get('authorize', lambda _: True),
                         trusted=kwargs.get('trusted', lambda: True), utcnow=lambda: NOW,
                         clock=kwargs.get('clock', lambda: 0))


@pytest.mark.asyncio
async def test_executor_claims_before_io_and_reports_partial_results_without_retry(tmp_path):
    saved = setup(store(tmp_path), config={**CONFIG, 'actions': [ACTION, {**ACTION, 'action': 'display'}]})
    calls = []
    async def dispatch(item, *, can_send):
        assert can_send()
        persisted = saved.storage.get_cache('room', 'scenes')['runs'][-1]
        assert persisted['steps'][len(calls)]['status'] == 'unknown'
        calls.append(item)
        return 'confirmed' if len(calls) == 1 else 'unconfirmed'
    engine = executor(saved, dispatch)
    result = await engine.run(trigger(), revision=saved.revision)
    assert [row['status'] for row in result['steps']] == ['confirmed', 'unconfirmed']
    assert len(calls) == 2 and result['finished'] and not saved.active


@pytest.mark.asyncio
@pytest.mark.parametrize('change', ['disable', 'authorization', 'clock', 'deadline'])
async def test_executor_revocation_during_preflight_cancels_and_skips_remaining(tmp_path, change):
    saved = setup(store(tmp_path), config={**CONFIG, 'actions': [ACTION, {**ACTION, 'action': 'display'}]})
    started, cancelled = asyncio.Event(), asyncio.Event()
    flags = {'authorization': True, 'clock': True, 'mono': 0}
    calls = []
    async def dispatch(item, *, can_send):
        started.set()
        try:
            await asyncio.Event().wait()
            assert can_send()
            calls.append(item)
        finally: cancelled.set()
    engine = executor(saved, dispatch, authorize=lambda _: flags['authorization'],
                      trusted=lambda: flags['clock'], clock=lambda: flags['mono'])
    task = asyncio.create_task(engine.run(trigger(), revision=saved.revision))
    await started.wait()
    if change == 'disable': saved.edit('morning', {'enabled': False, 'automatic': False, 'actions': [ACTION]}, revision=saved.revision)
    elif change == 'deadline': flags['mono'] = 121
    else: flags[change] = False
    result = await asyncio.wait_for(task, 2)
    assert cancelled.is_set() and calls == []
    assert [step['status'] for step in result['steps']] == ['unconfirmed', 'not_started']
    assert result['interrupted'] and not result['finished']


@pytest.mark.asyncio
async def test_executor_shutdown_cancels_dispatch_and_preserves_unknown_without_replay(tmp_path):
    saved = setup(store(tmp_path))
    started = asyncio.Event()
    async def dispatch(item, *, can_send):
        started.set()
        await asyncio.Event().wait()
    engine = executor(saved, dispatch)
    task = asyncio.create_task(engine.run(trigger(), revision=saved.revision))
    await started.wait()
    with pytest.raises(SceneStopped): await engine.run(trigger(), revision=saved.revision)
    await engine.close()
    with pytest.raises(asyncio.CancelledError): await task
    assert saved.runs[-1]['steps'][0]['status'] == 'unknown' and not saved.runs[-1]['finished']
    assert Scenes(saved.storage).configuration()['runs'][-1]['interrupted']
    assert Scenes(saved.storage).active is None
    with pytest.raises(SceneStopped): await engine.run(trigger(), revision=saved.revision)


@pytest.mark.asyncio
@pytest.mark.parametrize('outcome', ['skipped_override', 'unavailable', 'not_sent', 'bad', 'exception'])
async def test_executor_factual_outcomes_or_unknown_not_optimistic_success(tmp_path, outcome):
    saved = setup(store(tmp_path))
    calls = []
    async def dispatch(item, *, can_send):
        calls.append(item)
        if outcome == 'exception': raise OSError('No provider details may escape')
        return outcome
    result = await executor(saved, dispatch).run(trigger(), revision=saved.revision)
    assert result['steps'][0]['status'] == ('unconfirmed' if outcome in ('bad', 'exception') else outcome)
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_executor_denied_trigger_creates_no_claim_and_no_dispatch(tmp_path):
    saved = setup(store(tmp_path))
    async def dispatch(*args, **kwargs): pytest.fail('Must not call device')
    engine = executor(saved, dispatch, authorize=lambda _: False)
    with pytest.raises(SceneStopped): await engine.run(trigger(), revision=saved.revision)
    assert saved.runs == []


@pytest.mark.asyncio
async def test_uncooperative_dispatch_is_retained_and_poisoned_not_replaced(tmp_path):
    saved = setup(store(tmp_path))
    started, release = asyncio.Event(), asyncio.Event()
    gates = []
    async def dispatch(item, *, can_send):
        gates.append(can_send)
        started.set()
        try: await release.wait()
        except asyncio.CancelledError: await release.wait()
        return 'unconfirmed'
    engine = executor(saved, dispatch)
    task = asyncio.create_task(engine.run(trigger(), revision=saved.revision))
    await started.wait()
    try:
        await asyncio.wait_for(engine.cancel(), 4)
        assert engine.closed and engine.dispatch_task is not None
        assert not gates[0]()
        with pytest.raises(SceneStopped): await engine.run(trigger(), revision=saved.revision)
        with pytest.raises(asyncio.CancelledError): await task
    finally:
        child = engine.dispatch_task
        release.set()
        if child: await child


@pytest.mark.asyncio
async def test_ui_publish_failure_cannot_abandon_scene_journal(tmp_path):
    saved = setup(store(tmp_path))
    async def dispatch(item, *, can_send): return 'confirmed'
    def failed(): raise RuntimeError('Disconnected UI')
    engine = executor(saved, dispatch)
    engine.publish = failed
    result = await engine.run(trigger(), revision=saved.revision)
    assert result['finished'] and not engine.task and not saved.active


@pytest.mark.asyncio
async def test_dispatch_authorization_callback_expires_when_run_finishes(tmp_path):
    saved = setup(store(tmp_path))
    gates = []
    async def dispatch(item, *, can_send):
        gates.append(can_send)
        assert can_send()
        return 'confirmed'
    await executor(saved, dispatch).run(trigger(), revision=saved.revision)
    assert not gates[0]()

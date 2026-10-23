"""Private fake Wayland server; never connects to the owner's desktop."""
import os
from pathlib import Path
import socket
import struct
import sys
from threading import Thread
from unittest.mock import Mock, call

import pytest
from fastapi.testclient import TestClient

from luma.api import create_app
from luma.cursor_startup import MANAGER, StartupCursor, _endpoint, _string, _uints, park_pointer, refresh_pointer
from luma.cursor_refresh import CursorRefreshServer, SOCKET_NAME, notify_cursor_refresh

pytestmark = pytest.mark.skipif(not sys.platform.startswith('linux'), reason='Private Unix Wayland sockets')


@pytest.fixture
def graphical(tmp_path):
    root = tmp_path/'runtime'
    root.mkdir(mode=0o700)
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    path = root/'wayland-test'
    server.bind(str(path))
    server.listen(1)
    yield {'XDG_RUNTIME_DIR':str(root), 'WAYLAND_DISPLAY':path.name}, path, server
    server.close()


def test_marker_parks_once_across_bridge_restarts_and_again_for_new_compositor(graphical):
    env, path, _ = graphical
    clock = Mock(return_value=100.)
    park = Mock()
    cursor = StartupCursor(env=env, clock=clock, park=park)
    assert cursor.tick() == 'ok'
    park.assert_called_once_with(path)
    clock.return_value = 200.
    assert cursor.tick() == 'ok'
    assert StartupCursor(env=env, clock=clock, park=park).tick() == 'ok'
    park.assert_called_once()
    path.unlink()
    replacement = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        replacement.bind(str(path))
        replacement.listen(1)
        assert StartupCursor(env=env, clock=clock, park=park).tick() == 'ok'
        assert park.call_count == 2
    finally:
        replacement.close()


def test_failure_retries_without_claiming_park_or_interfering_with_other_controls(graphical):
    env, _, _ = graphical
    clock = Mock(return_value=100.)
    park = Mock(side_effect=OSError('Unavailable'))
    cursor = StartupCursor(env=env, clock=clock, park=park)
    assert cursor.tick() == 'unavailable; retrying'
    assert not list(Path(env['XDG_RUNTIME_DIR']).glob('luma-cursor-park-*'))
    clock.return_value = 104.
    cursor.tick()
    assert park.call_count == 1
    clock.return_value = 105.
    park.side_effect = None
    assert cursor.tick() == 'ok'
    assert park.call_count == 2


@pytest.mark.parametrize('unsafe', ['no_display', 'outside', 'relative_runtime', 'shared_runtime', 'socket_symlink', 'marker_symlink'])
def test_unsafe_socket_or_marker_is_not_used(graphical, tmp_path, unsafe):
    env, path, _ = graphical
    env = dict(env)
    if unsafe == 'no_display':
        del env['WAYLAND_DISPLAY']
    elif unsafe == 'outside':
        env['WAYLAND_DISPLAY'] = str(tmp_path/'outside-socket')
    elif unsafe == 'relative_runtime':
        env['XDG_RUNTIME_DIR'] = 'relative'
    elif unsafe == 'shared_runtime':
        path.parent.chmod(0o755)
    elif unsafe == 'socket_symlink':
        link = path.parent/'link'; link.symlink_to(path)
        env['WAYLAND_DISPLAY'] = link.name
    else:
        marker = _endpoint(env)[2]
        marker.symlink_to(tmp_path/'do-not-overwrite')
    park = Mock()
    assert StartupCursor(env=env, park=park).tick() == 'unavailable; retrying'
    park.assert_not_called()
    assert not (tmp_path/'do-not-overwrite').exists()


def receive(client):
    def exact(count):
        data = b''
        while len(data) < count:
            chunk = client.recv(count-len(data))
            if not chunk: raise EOFError()
            data += chunk
        return data
    sender, word = struct.unpack('=II', exact(8))
    size, opcode = word >> 16, word & 0xffff
    return sender, opcode, exact(size-8)


def event(client, sender, opcode, payload=b''):
    message = struct.pack('=II', sender, ((len(payload)+8)<<16)|opcode)+payload
    # Intentionally fragment frames to exercise stream reassembly.
    client.sendall(message[:5]); client.sendall(message[5:])


@pytest.mark.parametrize('action', ['park', 'refresh'])
@pytest.mark.parametrize('failure', [None, 'missing_protocol', 'display_error', 'invalid_size', 'disconnect', 'stall'])
def test_real_socket_roundtrips_park_at_exact_extent_without_buttons_or_keys(graphical, failure, action):
    _, path, server = graphical
    messages, errors = [], []
    def serve():
        try:
            client, _ = server.accept()
            with client:
                client.settimeout(3)
                while True:
                    try: sender, opcode, payload = receive(client)
                    except EOFError: return
                    messages.append((sender, opcode, payload))
                    if (sender, opcode) == (1, 1) and failure != 'missing_protocol':
                        event(client, 2, 0, _uints(17)+_string(MANAGER)+_uints(2))
                    if (sender, opcode) == (1, 0):
                        callback = struct.unpack('=I', payload)[0]
                        if failure == 'display_error':
                            event(client, 1, 0, _uints(1, 0)+_string('private error must not escape')); return
                        if failure == 'invalid_size':
                            client.sendall(struct.pack('=II', 1, 7 << 16)); return
                        if failure == 'disconnect': return
                        if failure == 'stall': continue
                        event(client, callback, 0, _uints(0))
        except BaseException as error:
            errors.append(error)
    thread = Thread(target=serve, daemon=True); thread.start()
    operation = park_pointer if action=='park' else refresh_pointer
    if failure:
        with pytest.raises((ValueError, OSError)):
            operation(path)
    else:
        operation(path)
    thread.join(timeout=4)
    assert not thread.is_alive() and not errors
    if not failure:
        bind = next(payload for sender, opcode, payload in messages if sender == 2)
        assert _string(MANAGER) in bind
        manager, pointer = 4, 5
        assert (manager, 0, _uints(0, pointer)) in messages
        if action=='park':
            motion = [payload for sender, opcode, payload in messages if (sender, opcode) == (pointer, 1)]
            assert len(motion) == 1
            assert struct.unpack('=IIIII', motion[0])[1:] == (1, 1, 1, 1)
            assert [opcode for sender, opcode, _ in messages if sender == pointer] == [1, 4, 8]
        else:
            motion = [payload for sender, opcode, payload in messages if (sender, opcode)==(pointer,0)]
            assert [struct.unpack('=Iii', payload)[1:] for payload in motion]==[(1,0),(-1,0)]
            assert [opcode for sender,opcode,_ in messages if sender==pointer]==[0,4,0,4,8]
        assert (manager, 1, b'') in messages


def test_cursor_report_is_fixed_local_diagnostic_only(tmp_path):
    app = create_app(data_dir=tmp_path)
    client = TestClient(app)
    assert client.post('/api/v1/device/report',json={'controls':{'cursor_startup':'ok'}}).status_code == 200
    assert client.post('/api/v1/device/report',json={'controls':{'cursor_startup':'unavailable; retrying'}}).status_code == 200
    assert client.post('/api/v1/device/report',json={'controls':{'cursor_startup':'arbitrary text'}}).status_code == 422
    remote = TestClient(app, client=('192.0.2.20',5000))
    assert remote.post('/api/v1/device/report',json={'controls':{'cursor_startup':'ok'}}).status_code == 403


def test_private_refresh_is_immediate_reversible_and_cleans_up(graphical):
    env,path,_ = graphical
    refresh = Mock()
    runtime=path.parent
    with CursorRefreshServer(env=env,refresh=refresh):
        assert notify_cursor_refresh(runtime=runtime)
        assert notify_cursor_refresh(runtime=runtime)  # Do not discard a fast hide→show.
        assert refresh.call_args_list==[call(path)]*2
        assert (runtime/SOCKET_NAME).stat().st_mode & 0o777 == 0o600
        with CursorRefreshServer(env=env,refresh=Mock()):
            assert notify_cursor_refresh(runtime=runtime)
        assert notify_cursor_refresh(runtime=runtime)  # Second helper did not unlink the first.
    assert not (runtime/SOCKET_NAME).exists()
    assert not notify_cursor_refresh(runtime=runtime)


@pytest.mark.parametrize('kind',['stale','regular','symlink','bad_command','failed_refresh'])
def test_refresh_rejects_unsafe_paths_and_payloads_without_input(graphical,tmp_path,kind):
    env,path,_ = graphical
    endpoint=path.parent/SOCKET_NAME
    refresh=Mock()
    if kind=='stale':
        with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as old:
            old.bind(str(endpoint))
    elif kind=='regular':
        endpoint.write_text('must survive')
    elif kind=='symlink':
        endpoint.symlink_to(tmp_path/'must-not-create')
    elif kind=='failed_refresh':
        refresh.side_effect=OSError('No graphical socket')
    with CursorRefreshServer(env=env,refresh=refresh):
        if kind=='bad_command':
            with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as client:
                client.settimeout(1);client.connect(str(endpoint));client.sendall(b'R;bad')
                assert client.recv(1)==b''
            refresh.assert_not_called()
        elif kind=='stale':
            assert notify_cursor_refresh(runtime=path.parent)
            refresh.assert_called_once_with(path)
        else:
            assert not notify_cursor_refresh(runtime=path.parent)
    if kind=='regular':
        assert endpoint.read_text()=='must survive'
    if kind=='symlink':
        assert endpoint.is_symlink() and not (tmp_path/'must-not-create').exists()


def test_cursor_refresh_api_is_local_only_and_has_no_input_parameters(tmp_path,monkeypatch):
    refresh=Mock(return_value=True)
    monkeypatch.setattr('luma.api.notify_cursor_refresh',refresh)
    app=create_app(data_dir=tmp_path)
    local=TestClient(app)
    assert local.post('/api/v1/device/cursor-refresh').json()=={'refreshed':True}
    refresh.assert_called_once_with()
    remote=TestClient(app,client=('192.0.2.20',5000))
    token=app.state.security.get_or_create_lan_token()
    assert remote.post('/api/v1/device/cursor-refresh',headers={'X-Luma-Token':token}).status_code==403
    assert local.post('/api/v1/device/cursor-refresh',headers={'Origin':'https://evil.example'}).status_code==403
    refresh.assert_called_once()

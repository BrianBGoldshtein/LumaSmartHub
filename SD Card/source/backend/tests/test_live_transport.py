"""Actual Uvicorn TCP/WebSocket coverage: TestClient cannot catch missing WS extras."""
import json
import socket
import threading
import time

import httpx
import uvicorn
from websockets.sync.client import connect

from luma.api import create_app


def test_live_socket_delivers_timer_completion_without_reload(tmp_path):
    app=create_app(data_dir=tmp_path)
    clock=[0.]
    app.state.luma.timer.clock=lambda:clock[0]
    listener=socket.socket(socket.AF_INET,socket.SOCK_STREAM)
    listener.bind(('127.0.0.1',0))
    port=listener.getsockname()[1]
    server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=port,log_level='error',access_log=False,proxy_headers=False))
    thread=threading.Thread(target=server.run,kwargs={'sockets':[listener]},daemon=True)
    thread.start()
    try:
        deadline=time.monotonic()+5
        while not server.started and thread.is_alive() and time.monotonic()<deadline:
            time.sleep(.01)
        assert server.started, 'Real ASGI server did not start'
        with connect(f'ws://127.0.0.1:{port}/api/v1/events',proxy=None,open_timeout=3,close_timeout=1) as websocket:
            first=json.loads(websocket.recv(timeout=3))
            assert first['data']['privacy_redacted'] is True
            with httpx.Client(base_url=f'http://127.0.0.1:{port}',trust_env=False,timeout=3) as client:
                result=client.post('/api/v1/commands',json={'name':'start_timer','value':1})
                assert result.status_code==200 and result.json()['result']['accepted']
                clock[0]=61
                deadline=time.monotonic()+5
                while time.monotonic()<deadline:
                    message=json.loads(websocket.recv(timeout=3))
                    if message.get('data',{}).get('timer',{}).get('status')=='complete':
                        assert message['data']['privacy_redacted']
                        break
                else:
                    raise AssertionError('Completion was never pushed to the real socket')
                assert client.post('/api/v1/device/timer-chime').json()=={'play':True}
                assert client.post('/api/v1/device/timer-chime').json()=={'play':False}
    finally:
        server.should_exit=True
        thread.join(timeout=5)
        listener.close()
        assert not thread.is_alive(), 'Test server must not survive the test'

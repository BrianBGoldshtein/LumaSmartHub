"""Isolated Linux labwc/Chromium frame-clock diagnostic; no real outputs.

Runs an input-free local test page which reports ONLY frame counters and its
visibility flag. No browser automation, accounts, screenshots or personal data.
Use the private-mount-namespace invocation documented for keyboard-smoke.py.
This tests compositor/browser liveness, not a physical Pi or panel brightness.
"""
import json
import os
from pathlib import Path
import signal
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from tempfile import TemporaryDirectory, TemporaryFile
import time


PAGE = b'''<!doctype html><html style="background:black;color:white"><title>Luma frame diagnostic</title>
<body style="background:black">Software-only frame diagnostic<script>
let frames=0;function frame(){frames++;requestAnimationFrame(frame)}requestAnimationFrame(frame);
setInterval(()=>fetch('/telemetry',{method:'POST',headers:{'Content-Type':'application/json'},
body:JSON.stringify({frames,hidden:document.hidden})}).catch(()=>{}),500);
</script></body></html>'''


class Telemetry(BaseHTTPRequestHandler):
    latest = None
    received = 0.
    def log_message(self, *_):
        pass
    def do_GET(self):
        self.send_response(200 if self.path=='/' else 404)
        self.send_header('Content-Type','text/html'); self.end_headers()
        if self.path=='/': self.wfile.write(PAGE)
    def do_POST(self):
        length=int(self.headers.get('Content-Length','0'))
        if self.path!='/telemetry' or not 0<length<=256:
            self.send_error(400);return
        try:
            payload=json.loads(self.rfile.read(length))
            if set(payload)!={'frames','hidden'} or type(payload['frames']) is not int or type(payload['hidden']) is not bool:
                raise ValueError()
            type(self).latest=payload;type(self).received=time.monotonic()
        except (ValueError,TypeError):
            self.send_error(400);return
        self.send_response(204);self.end_headers()


def stop(process):
    if process and process.poll() is None:
        os.killpg(process.pid,signal.SIGTERM)
        try:process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid,signal.SIGKILL);process.wait(timeout=5)


def sample(label, seconds=4):
    begin=Telemetry.latest
    time.sleep(seconds)
    end=Telemetry.latest
    if begin is None or end is None:
        raise RuntimeError('Test page did not report frame counters')
    result={'phase':label,'frames':end['frames']-begin['frames'],'hidden':end['hidden'],
            'telemetry_age_seconds':round(time.monotonic()-Telemetry.received,2)}
    print(json.dumps(result),flush=True)
    return result


def main():
    if os.name!='posix' or os.geteuid()==0:
        raise SystemExit('Run as a normal Linux build user, never on the real display.')
    with TemporaryDirectory(prefix='luma-display-smoke-') as directory, TemporaryFile() as logs:
        root=Path(directory);config=root/'config';config.mkdir()
        env={k:v for k,v in os.environ.items() if k not in {'DISPLAY','WAYLAND_DISPLAY','DBUS_SESSION_BUS_ADDRESS'}}
        env.update(XDG_RUNTIME_DIR=directory,XDG_CONFIG_HOME=str(config),XDG_CONFIG_DIRS=str(config),
                   WLR_BACKENDS='headless',WLR_RENDERER='pixman',WLR_HEADLESS_OUTPUTS='1',LABWC_UPDATE_ACTIVATION_ENV='0')
        compositor=subprocess.Popen(['/usr/bin/labwc','-C',str(config)],env=env,stdin=subprocess.DEVNULL,
                                    stdout=logs,stderr=logs,start_new_session=True)
        browser=None
        server=ThreadingHTTPServer(('127.0.0.1',0),Telemetry)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            deadline=time.monotonic()+10
            while True:
                sockets=[path for path in root.glob('wayland-*') if path.is_socket()]
                if sockets:
                    env['WAYLAND_DISPLAY']=sockets[0].name;break
                if compositor.poll() is not None or time.monotonic()>deadline:
                    raise RuntimeError('Private headless compositor did not start')
                time.sleep(.1)
            def output(*args):
                return subprocess.run(['/usr/bin/wlr-randr',*args],env=env,check=True,capture_output=True,text=True,timeout=8).stdout
            monitors=json.loads(output('--json'))
            if len(monitors)!=1 or not monitors[0]['name'].startswith('HEADLESS-'):
                raise RuntimeError('Refusing to operate a non-test output')
            name=monitors[0]['name']
            for label,flags in [('normal',[]),('foreground-flags',['--disable-background-timer-throttling','--disable-renderer-backgrounding','--disable-backgrounding-occluded-windows'])]:
                Telemetry.latest=None
                browser=subprocess.Popen(['/usr/bin/chromium', '--kiosk','--no-first-run','--disable-component-update',
                    '--disable-features=Translate,MediaRouter','--ozone-platform=wayland',
                    f'--user-data-dir={root/label}',f'--app=http://127.0.0.1:{server.server_port}/',*flags],
                    env=env,stdin=subprocess.DEVNULL,stdout=logs,stderr=logs,start_new_session=True)
                deadline=time.monotonic()+25
                while Telemetry.latest is None:
                    if browser.poll() is not None or time.monotonic()>deadline:
                        raise RuntimeError('Isolated Chromium test page did not start')
                    time.sleep(.1)
                active=sample(label+':on')
                output('--output',name,'--off')
                time.sleep(1)
                off=sample(label+':off')
                output('--output',name,'--on')
                time.sleep(1)
                resumed=sample(label+':resumed')
                if active['frames']<=0 or resumed['frames']<=0:
                    raise RuntimeError('Active/resumed browser did not render')
                print(json.dumps({'configuration':label,'raf_runs_while_off':off['frames']>0}),flush=True)
                stop(browser);browser=None
        except Exception:
            logs.seek(0);print(logs.read().decode(errors='replace')[-5000:],flush=True)
            raise
        finally:
            stop(browser);stop(compositor);server.shutdown();server.server_close();thread.join(timeout=2)
    print('Diagnostic only: no physical outputs, user input, accounts or pixels inspected.',flush=True)


if __name__=='__main__':main()

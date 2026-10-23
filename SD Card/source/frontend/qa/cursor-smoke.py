"""Real labwc/Wayland/Chromium cursor pixels on a private headless output only.

Run as a normal build user in the private mount namespace used by
image-builder/keyboard-smoke.py. Requires build-host grim and Pillow only.
No owner's browser, keyboard, accounts, physical display or input device.
"""
import argparse
import json
import os
from pathlib import Path
import signal
import struct
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from PIL import Image, ImageChops

sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'backend/src'))
from luma.cursor_startup import MANAGER, StartupCursor, _WaylandPointer, _uints, _string
from luma.cursor_refresh import CursorRefreshServer, notify_cursor_refresh


PAGE = b'''<!doctype html><html><head><link rel="stylesheet" href="/styles.css"></head>
<body style="background:#263645;width:100vw;height:100vh;margin:0;overflow:hidden">
<div id="tiles" style="position:absolute;inset:0;pointer-events:none"></div>
<script type="module">
import {installIdleCursor} from '/idleCursor.js';
installIdleCursor(document,document.documentElement,20000,setTimeout,clearTimeout,
  ()=>requestAnimationFrame(()=>requestAnimationFrame(()=>fetch('/cursor-refresh',{method:'POST'}))));
let position={x:0,y:0,screenX:0,screenY:0},moves=0,touches=0;
document.addEventListener('pointermove',e=>{if(e.isTrusted){position={x:e.clientX,y:e.clientY,screenX:e.screenX,screenY:e.screenY};moves++;}},true);
document.addEventListener('pointerdown',()=>touches++,true);
// Continuous same-position events plus changing elements reproduce the old
// keepalive flaw without injecting any native input into another surface.
setInterval(()=>{
  const e=new PointerEvent('pointermove',{pointerType:'mouse',screenX:position.screenX,screenY:position.screenY,movementX:0,movementY:0});
  document.dispatchEvent(e);
  document.querySelector('#tiles').replaceChildren(document.createElement('div'));
},75);
setInterval(()=>fetch('/telemetry',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({
  ...position,moves,touches,width:innerWidth,height:innerHeight,
  idle:document.documentElement.classList.contains('luma-cursor-idle'),
  cursor:getComputedStyle(document.body).cursor,at:performance.now()
})}),100);
</script></body></html>'''


class Handler(BaseHTTPRequestHandler):
    latest = None
    module = b''
    style = b''
    runtime = None
    refreshes = 0
    def log_message(self, *_): pass
    def do_GET(self):
        data = {'/':PAGE, '/idleCursor.js':self.module, '/styles.css':self.style}.get(self.path)
        if data is None:
            self.send_error(404); return
        self.send_response(200)
        self.send_header('Content-Type','text/javascript' if self.path.endswith('.js') else 'text/css' if self.path.endswith('.css') else 'text/html')
        self.end_headers(); self.wfile.write(data)
    def do_POST(self):
        if self.path=='/cursor-refresh':
            refreshed=notify_cursor_refresh(runtime=self.runtime)
            type(self).refreshes+=int(refreshed)
            self.send_response(200);self.end_headers();return
        size = int(self.headers.get('Content-Length','0'))
        if self.path != '/telemetry' or not 0 < size <= 2048:
            self.send_error(400); return
        type(self).latest = json.loads(self.rfile.read(size))
        self.send_response(204); self.end_headers()


def wait(check, seconds=10):
    deadline = time.monotonic()+seconds
    while not check():
        if time.monotonic()>deadline: raise RuntimeError('Private cursor check timed out')
        time.sleep(.05)


def stop(process):
    if process and process.poll() is None:
        os.killpg(process.pid,signal.SIGTERM)
        try: process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid,signal.SIGKILL); process.wait(timeout=5)


def main():
    args = argparse.ArgumentParser(description=__doc__)
    args.add_argument('--module',required=True,type=Path)
    args.add_argument('--output',required=True,type=Path)
    values = args.parse_args()
    if os.name != 'posix' or os.geteuid()==0:
        raise SystemExit('Use a normal build user, never the real display.')
    root = values.output.resolve()
    root.mkdir(mode=0o700)
    runtime = root/'runtime'; runtime.mkdir(mode=0o700)
    config = root/'config'; config.mkdir()
    Handler.module = values.module.read_bytes()
    Handler.style = (Path(__file__).resolve().parents[1]/'src/styles.css').read_bytes()
    Handler.runtime = runtime
    env = {k:v for k,v in os.environ.items() if k not in {'DISPLAY','WAYLAND_DISPLAY','DBUS_SESSION_BUS_ADDRESS','WAYLAND_SOCKET'}}
    env.update(XDG_RUNTIME_DIR=str(runtime),XDG_CONFIG_HOME=str(config),XDG_CONFIG_DIRS=str(config),
               WLR_BACKENDS='headless',WLR_RENDERER='pixman',WLR_HEADLESS_OUTPUTS='1',LABWC_UPDATE_ACTIVATION_ENV='0')
    server = ThreadingHTTPServer(('127.0.0.1',0),Handler)
    thread = threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    compositor = browser = pointer = None
    with (root/'compositor.log').open('w') as logs, CursorRefreshServer(env=env):
        try:
            compositor = subprocess.Popen(['/usr/bin/labwc','-C',str(config)],env=env,stdin=subprocess.DEVNULL,stdout=logs,stderr=logs,start_new_session=True)
            wait(lambda: any(p.is_socket() for p in runtime.glob('wayland-*')))
            sock = next(p for p in runtime.glob('wayland-*') if p.is_socket())
            env['WAYLAND_DISPLAY'] = sock.name
            outputs = json.loads(subprocess.run(['wlr-randr','--json'],env=env,check=True,capture_output=True,text=True,timeout=5).stdout)
            if len(outputs)!=1 or not outputs[0]['name'].startswith('HEADLESS-'):
                raise RuntimeError('Refusing to operate a non-test output')
            pointer = _WaylandPointer(sock)
            name,_ = pointer.globals[MANAGER]
            manager, device = pointer.allocate(),pointer.allocate()
            pointer.send(2,0,_uints(name)+_string(MANAGER)+_uints(1,manager))
            pointer.send(manager,0,_uints(0,device));pointer.roundtrip()
            def motion(x,y,width,height):
                pointer.deadline=time.monotonic()+2
                pointer.send(device,1,_uints(int(time.monotonic()*1000)&0xffffffff,x,y,width,height))
                pointer.send(device,4);pointer.roundtrip()
            browser = subprocess.Popen(['/usr/bin/chromium','--kiosk','--no-first-run','--disable-component-update',
                '--disable-features=Translate,MediaRouter','--ozone-platform=wayland',
                f'--user-data-dir={root/"chromium"}',f'--app=http://127.0.0.1:{server.server_port}/'],
                env=env,stdin=subprocess.DEVNULL,stdout=logs,stderr=logs,start_new_session=True)
            wait(lambda: Handler.latest is not None,30)
            width,height = Handler.latest['width'],Handler.latest['height']
            motion(width//2,height//2,width,height)
            wait(lambda: Handler.latest['moves']>0)
            if StartupCursor(env=env).tick()!='ok': raise RuntimeError('Native startup parking failed')
            # The exact output boundary can be outside the client's hit region,
            # so sample one physical pixel inward to observe the native warp.
            pointer.deadline=time.monotonic()+2
            pointer.send(device,0,struct.pack('=Iii',int(time.monotonic()*1000)&0xffffffff,-256,-256))
            pointer.send(device,4);pointer.roundtrip()
            wait(lambda: Handler.latest['x']>=width-3 and Handler.latest['y']>=height-3)
            corner = dict(Handler.latest)
            # Keep this virtual test mouse alive, like a real attached USB mouse.
            motion(width//2,height//2,width,height)
            wait(lambda: abs(Handler.latest['x']-width//2)<2 and not Handler.latest['idle'])
            def cursor_pixels(label):
                with_cursor = root/f'{label}-cursor.png'
                subprocess.run(['grim','-c',str(with_cursor)],env=env,check=True,timeout=5,stdout=subprocess.DEVNULL)
                # Pixman can include a software cursor even without grim -c.
                # Compare against this fixture's known uniform background,
                # not two captures that might both contain the same cursor.
                image = Image.open(with_cursor).convert('RGB')
                plain = Image.new('RGB',image.size,image.getpixel((0,0)))
                return sum(value!=(0,0,0) for value in ImageChops.difference(image,plain).getdata())
            visible_pixels = cursor_pixels('active')
            if visible_pixels<5: raise RuntimeError('Positive control failed: no visible native cursor')
            start=time.monotonic()
            wait(lambda: Handler.latest['idle'] and Handler.latest['cursor']=='none',22)
            elapsed=time.monotonic()-start
            wait(lambda: Handler.refreshes>=1)
            time.sleep(.2)
            hidden_pixels=cursor_pixels('idle')
            if hidden_pixels or not Handler.latest['idle']:
                raise RuntimeError('Native cursor did not stay hidden')
            # The runtime marker must not re-park a mouse already in use.
            before=Handler.latest['moves']
            if StartupCursor(env=env).tick()!='ok': raise RuntimeError('Bridge-restart marker failed')
            time.sleep(.3)
            if Handler.latest['moves']!=before: raise RuntimeError('Bridge restart moved an active mouse')
            motion(width//2+10,height//2,width,height)
            wait(lambda: not Handler.latest['idle'])
            wait(lambda: Handler.refreshes>=2)
            time.sleep(.2)
            restored_pixels=cursor_pixels('restored')
            if restored_pixels<5 or Handler.latest['touches']!=0:
                raise RuntimeError('Cursor restoration or no-click invariant failed')
            report={'scope':'Private headless labwc and native Wayland Chromium; no physical Pi',
                'viewport':[width,height],'startup_normalized_corner':[1,1],'one_pixel_inward_probe':[corner['x'],corner['y']],
                'idle_seconds':round(elapsed,2),'active_cursor_pixels':visible_pixels,
                'idle_cursor_pixels':hidden_pixels,'restored_cursor_pixels':restored_pixels,
                'same_position_events_every_ms':75,'native_refreshes':Handler.refreshes,
                'bridge_restart_does_not_warp':True,'clicks':0}
            (root/'result.json').write_text(json.dumps(report,indent=2)+'\n')
            print(json.dumps(report),flush=True)
        except BaseException:
            print(json.dumps({'last_telemetry':Handler.latest}),flush=True)
            raise
        finally:
            if pointer: pointer.close()
            stop(browser);stop(compositor);server.shutdown();server.server_close();thread.join(timeout=2)


if __name__=='__main__': main()

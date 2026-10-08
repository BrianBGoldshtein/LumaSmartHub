"""Loopback-only browser QA fixture. No Google account, real updater or audio."""
import os
from pathlib import Path
import tempfile

from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.routing import APIRoute
import uvicorn

from luma.api import create_app

temporary = tempfile.TemporaryDirectory(prefix='luma-google-browser-')
app = create_app(data_dir=Path(temporary.name), frontend_dir=os.environ['LUMA_FRONTEND_DIR'])
fixture = {'settings_failed':False, 'update_failed':False, 'state':'idle', 'version':'0.2.10', 'consents':0}


async def control(payload: dict):
    fixture.update(payload)
    return {'ok':True}


async def settings():
    if fixture['settings_failed']:
        return JSONResponse({'detail':'Synthetic local settings outage'},status_code=503)
    return app.state.luma.snapshot()['settings']


async def google_status():
    return {'configured':True,'authorized':True,'task_updates':False,'reconnect_required':True}


async def catalog():
    return JSONResponse({'detail':'Synthetic renewal required'},status_code=409)


async def authorize():
    fixture['consents'] += 1
    return {'url':'http://127.0.0.1:18874/_qa/consent'}


async def consent():
    return HTMLResponse('<h1>Synthetic Google consent reached</h1>')


async def update_status():
    return {'current_version':fixture['version'],'state':fixture['state'],
            'target_version':'0.2.11','phase':'failed' if fixture['state']=='failed' else 'complete'}


async def update_check():
    return {'current_version':'0.2.10','state':'available','version':'0.2.11','candidate_id':'synthetic-only'}


async def update_install():
    fixture['state'] = 'failed' if fixture['update_failed'] else 'installed'
    fixture['version'] = '0.2.10' if fixture['update_failed'] else '0.2.11'
    return {'accepted':True}


for path, endpoint, methods in [
    ('/_qa/control',control,['POST']), ('/_qa/consent',consent,['GET']),
    ('/api/v1/settings',settings,['GET']), ('/api/v1/google/status',google_status,['GET']),
    ('/api/v1/google/calendars',catalog,['GET']), ('/api/v1/google/event-colors',catalog,['GET']),
    ('/api/v1/google/authorize',authorize,['POST']), ('/api/v1/updates/status',update_status,['GET']),
    ('/api/v1/updates/check',update_check,['POST']), ('/api/v1/updates/install',update_install,['POST']),
]:
    app.router.routes.insert(0,APIRoute(path,endpoint,methods=methods))


if __name__ == '__main__':
    uvicorn.run(app,host='127.0.0.1',port=18874,access_log=False)

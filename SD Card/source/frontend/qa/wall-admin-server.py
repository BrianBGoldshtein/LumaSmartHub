"""Disposable wall PIN lab. No daemon workers, account, owner radio or broker."""
from contextlib import asynccontextmanager
import os

from fastapi import Request
from luma.api import create_app

app=create_app(data_dir=os.environ['WALL_QA_DATA'],frontend_dir=os.environ['WALL_QA_FRONTEND'])
app.state.security.set_pin('123456')
app.state.luma.update_settings({'onboarding_completed':True})
app.state.luma.display_clock_trusted=lambda:True
clock=[0.0]
app.state.admin.clock=lambda:clock[0]

@asynccontextmanager
async def isolated(_):
    yield  # Never start Bluetooth/network/provider/device workers in this lab.
app.router.lifespan_context=isolated

@app.middleware('http')
async def qa_only(request:Request,call_next):
    if request.url.path=='/qa/theme':
        from fastapi.responses import JSONResponse
        value=await request.json()
        app.state.luma.update_settings({'theme':value['theme']})
        return JSONResponse({'changed':True})
    if request.url.path=='/qa/expire':
        from fastapi.responses import JSONResponse
        clock[0]+=301
        return JSONResponse({'expired':True})
    return await call_next(request)

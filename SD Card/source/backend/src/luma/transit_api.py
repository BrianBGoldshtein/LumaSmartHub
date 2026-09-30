"""Owner-local transit setup. Token input never enters validation responses."""
import asyncio
import json
from datetime import UTC,datetime
from typing import Literal

from fastapi import Depends,HTTPException,Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel,Field

from .transit_runtime import TransitRuntime
from .transit_transport import TransitUnavailable,TransitQuota


class DirectoryRequest(BaseModel):
    model_config={'extra':'forbid'}
    kind:Literal['operators','lines','stops']
    operator_id:str|None=Field(default=None,min_length=1,max_length=160)
    line_id:str|None=Field(default=None,min_length=1,max_length=160)
    query:str=Field(default='',max_length=100)
    page:int=Field(default=0,ge=0,le=250)
    refresh:bool=Field(default=False,strict=True)


class FavoriteRequest(BaseModel):
    model_config={'extra':'forbid'}
    title:str=Field(min_length=1,max_length=100)
    operator_id:str=Field(min_length=1,max_length=160)
    stop_id:str=Field(min_length=1,max_length=160)
    route_id:str|None=Field(default=None,min_length=1,max_length=160)
    direction:str|None=Field(default=None,min_length=1,max_length=160)
    public:bool=Field(default=False,strict=True)
    item_id:str|None=Field(default=None,pattern=r'^[a-f0-9-]{36}$')
    revision:str|None=Field(default=None,pattern=r'^[a-f0-9-]{36}$')


class Revision(BaseModel):
    model_config={'extra':'forbid'}
    revision:str=Field(pattern=r'^[a-f0-9-]{36}$')


class FavoriteId(BaseModel):
    model_config={'extra':'forbid'}
    item_id:str|None=Field(default=None,pattern=r'^[a-f0-9-]{36}$')


class PreviewRequest(BaseModel):
    model_config={'extra':'forbid'}
    operator_id:str=Field(min_length=1,max_length=160)
    stop_id:str=Field(min_length=1,max_length=160)
    route_id:str|None=Field(default=None,min_length=1,max_length=160)


def install_transit_api(app,service,local_only):
    runtime=TransitRuntime(service);app.state.transit_runtime=runtime

    def owner_access():
        if service.settings.onboarding_completed and service.snapshot()['privacy_redacted']:
            raise HTTPException(403,'Unlock private information to configure transit.')

    def configuration():
        return JSONResponse(service.transit.configuration(datetime.now(UTC)),headers={'Cache-Control':'no-store'})

    def changed(action):
        try:action()
        except ValueError as exc:raise HTTPException(409,str(exc)) from None
        service.publish('transit.updated');return configuration()

    async def provider(action):
        try:return await action()
        except TransitQuota:raise HTTPException(429,'Transit request allowance reached. Saved stops are unchanged; wait before retrying.') from None
        except (TransitUnavailable,ValueError):raise HTTPException(409,'Could not verify this transit selection. Check the token and reload the directory.') from None
        except Exception:raise HTTPException(502,'Transit is unavailable. Saved stops are unchanged.') from None

    @app.get('/api/v1/transit',dependencies=[Depends(local_only)])
    async def settings():
        owner_access();return configuration()

    @app.post('/api/v1/transit/token',dependencies=[Depends(local_only)])
    async def token(request:Request):
        owner_access();raw=bytearray()
        try:
            async with asyncio.timeout(3):
                async for chunk in request.stream():
                    if len(raw)+len(chunk)>1024:raise ValueError()
                    raw.extend(chunk)
            payload=json.loads(raw)
            if not isinstance(payload,dict) or set(payload)!={'token'}:raise ValueError()
            owner_access()
            service.transit.set_token(payload['token'])
        except (ValueError,TypeError,TimeoutError):raise HTTPException(422,'Enter a valid 511 token, or explicitly remove the saved token.') from None
        owner_access();service.publish('transit.updated');return configuration()

    @app.post('/api/v1/transit/directory',dependencies=[Depends(local_only)])
    async def directory(payload:DirectoryRequest):
        owner_access()
        rows=await provider(lambda:runtime.discover(payload.kind,operator_id=payload.operator_id,line_id=payload.line_id,force=payload.refresh))
        owner_access()
        query=payload.query.strip().casefold()
        rows=[row for row in rows if query in row['name'].casefold() or query in row['id'].casefold()]
        start=payload.page*40
        return JSONResponse({'items':rows[start:start+40],'page':payload.page,'total':len(rows),
                             'has_more':start+40<len(rows)},headers={'Cache-Control':'no-store'})

    @app.post('/api/v1/transit/favorites',dependencies=[Depends(local_only)])
    async def save(payload:FavoriteRequest):
        owner_access()
        if payload.item_id is None and len(service.transit.items)>=6:raise HTTPException(409,'Keep at most six transit favorites.')
        selection=await provider(lambda:runtime.verified_selection(operator_id=payload.operator_id,stop_id=payload.stop_id,route_id=payload.route_id))
        owner_access()
        return changed(lambda:service.transit.save(**selection,title=payload.title,direction=payload.direction,
                       public=payload.public,item_id=payload.item_id,revision=payload.revision))

    @app.post('/api/v1/transit/preview',dependencies=[Depends(local_only)])
    async def preview(payload:PreviewRequest):
        owner_access()
        result=await provider(lambda:runtime.preview(**payload.model_dump()))
        owner_access()
        return JSONResponse(result,headers={'Cache-Control':'no-store'})

    @app.delete('/api/v1/transit/favorites/{item_id}',dependencies=[Depends(local_only)])
    async def remove(item_id:str,payload:Revision):
        owner_access();return changed(lambda:service.transit.remove(item_id,payload.revision))

    @app.post('/api/v1/transit/refresh',dependencies=[Depends(local_only)])
    async def refresh(payload:FavoriteId):
        owner_access()
        attempted=await provider(lambda:runtime.refresh(payload.item_id))
        owner_access()
        if not attempted:raise HTTPException(429,'Transit is resting, unconfigured, or recently refreshed. Saved data is retained.')
        return configuration()

    @app.post('/api/v1/transit/visible',dependencies=[Depends(local_only)])
    async def visible(payload:FavoriteId):
        # A public transit slide may be visible during privacy standby. Only its
        # already-visible favorite may influence polling; this never unlocks data.
        views=service.snapshot().get('transit',[])
        if payload.item_id is not None and not any(row['id']==payload.item_id for row in views):raise HTTPException(403,'Transit favorite is not visible.')
        runtime.show(payload.item_id)
        return {'ok':True}

    return runtime

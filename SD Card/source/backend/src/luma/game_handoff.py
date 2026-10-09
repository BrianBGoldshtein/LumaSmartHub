"""Volatile wall-browser checkpoint handoff for primary remote USB backups."""
import asyncio
import secrets

from fastapi import Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from .portable_backup import _safe_games, PortableBackupError


class Reply(BaseModel):
    model_config = ConfigDict(extra='forbid')
    nonce: str = Field(pattern=r'^[A-Za-z0-9_-]{43}$')
    ok: bool = Field(strict=True)
    games: dict = Field(default_factory=dict)


class GameHandoff:
    def __init__(self):
        self.lock = asyncio.Lock()
        self.pending = None
        self.future = None

    async def operation(self, action, games, check):
        async with self.lock:
            check()
            self.future = asyncio.get_running_loop().create_future()
            self.pending = {'nonce': secrets.token_urlsafe(32), 'action': action, 'games': games}
            try:
                async with asyncio.timeout(12):
                    result = await self.future
                check()
                return result
            except TimeoutError:
                raise HTTPException(503, 'The wall screen did not confirm its game saves. Open the Luma dashboard and try again; do not repeat an uncertain restore.') from None
            finally:
                self.pending = self.future = None

    async def capture(self, check):
        return await self.operation('capture', {}, check)

    async def restore(self, games, check):
        return await self.operation('restore', _safe_games(games), check)


def install_game_handoff(app, local_only):
    handoff = app.state.game_handoff = GameHandoff()

    @app.get('/api/v1/backups/game-handoff', dependencies=[Depends(local_only)])
    async def pending():
        return handoff.pending or {'action': 'idle'}

    @app.post('/api/v1/backups/game-handoff', dependencies=[Depends(local_only)])
    async def acknowledge(reply: Reply, request: Request):
        if request.scope.get('luma_companion_check') is not None:
            raise HTTPException(403, 'Wall browser only.')
        if not handoff.pending or reply.nonce != handoff.pending['nonce'] or handoff.future.done():
            raise HTTPException(409, 'Checkpoint request expired.')
        try:
            games = _safe_games(reply.games)
        except PortableBackupError:
            raise HTTPException(422, 'Game checkpoint invalid.') from None
        if reply.ok:
            handoff.future.set_result(games)
        else:
            handoff.future.set_exception(HTTPException(503, 'The wall screen could not preserve its game saves.'))
        return {'accepted': True}

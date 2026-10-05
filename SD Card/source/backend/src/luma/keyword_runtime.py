"""Lifecycle for the signed acoustic asset, never a microphone/identity gate.

Download/install is serialized with the appliance's voice checks. Installation
readiness is deliberately separate from selecting or calibrating a detector.
"""
import asyncio
import os
from pathlib import Path
import re
import sys

from fastapi import Depends, HTTPException
from pydantic import BaseModel, ConfigDict

from . import keyword_asset


class KeywordConsent(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    confirmed: bool


class KeywordAssetRuntime:
    def __init__(self, data_root: Path, *, busy_check=lambda: False):
        self.data_root = data_root
        self.root = data_root / 'keyword-assets'
        self.busy_check = busy_check
        self.task: asyncio.Task | None = None
        self.phase: str | None = None
        self.error: str | None = None
        self.closing = False

    @property
    def busy(self):
        return self.task is not None and not self.task.done()

    def supported(self):
        # Tests/previews using a temporary data directory cannot accidentally
        # download models merely because they inherited the system image env.
        return (sys.platform == 'linux'
                and os.environ.get('LUMA_DATA_DIR') == '/var/lib/luma'
                and self.data_root == Path('/var/lib/luma')
                and keyword_asset._runtime_supported())

    def status(self):
        result = keyword_asset.status(self.root)
        if self.busy and result['phase'] not in {
                'checking', 'downloading', 'verifying', 'installing', 'recovering'}:
            result['phase'] = self.phase or 'queued'
        if self.error:
            result.update(phase='failed', error=self.error)
        return {**result, 'job_active': self.busy,
                'runtime_supported': self.supported(),
                'model_id': keyword_asset.KEYWORD_ID,
                'asset_version': keyword_asset.ASSET_VERSION}

    def start(self, *, repair=False, recovery_only=False):
        if self.closing:
            raise HTTPException(409, 'Luma is stopping. Retry after startup.')
        if not self.supported():
            raise HTTPException(409, 'The signed wake model installs on the Raspberry Pi only.')
        if self.busy:
            raise HTTPException(409, 'The wake model is already being prepared.')
        if self.busy_check():
            raise HTTPException(409, 'Finish the current voice check, sample or model installation first.')
        if repair and not keyword_asset.ready(self.root):
            raise HTTPException(409, 'Prepare the signed wake model before repairing it.')
        self.error = None
        self.phase = 'recovering' if recovery_only else 'queued'
        self.task = asyncio.create_task(self._prepare(repair, recovery_only))
        return self.status()

    async def _prepare(self, repair, recovery_only):
        try:
            self.phase = 'recovering'
            await asyncio.to_thread(keyword_asset.recover_interrupted_install, self.root)
            if not recovery_only:
                self.phase = 'checking'
                await asyncio.to_thread(keyword_asset.fetch_and_install,
                                        root=self.root, replace_existing=repair)
        except Exception as error:
            # Only fixed module error codes reach the UI; never an HTTP body,
            # local path, credential or traceback from a native install.
            code = str(error) if isinstance(error, keyword_asset.KeywordAssetError) else ''
            self.error = code if re.fullmatch('keyword_[a-z_]{1,64}', code) else 'keyword_install_failed'
        finally:
            self.phase = None

    async def run(self, *, initial_delay=20, retry_seconds=900):
        """Native-only delayed preparation; manual buttons share this job.

        A saved interruption journal is recovered even when a ready marker
        exists. Retries are bounded, never concurrent with a microphone trial.
        """
        if not self.supported():
            return
        await asyncio.sleep(initial_delay)
        first = True
        while not self.closing:
            if self.busy or self.busy_check():
                await asyncio.sleep(5)
                continue
            if first or not keyword_asset.ready(self.root):
                try:
                    self.start(recovery_only=first and keyword_asset.ready(self.root))
                except HTTPException:
                    await asyncio.sleep(5)
                    continue
                first = False
                await asyncio.shield(self.task)
            await asyncio.sleep(retry_seconds)

    async def close(self):
        self.closing = True
        # Cancelling to_thread does not stop its installer. Keep it owned and
        # join it rather than starting a second transaction during shutdown.
        # The OS stop deadline/power-loss journal remains the final safeguard.
        if self.busy:
            await asyncio.shield(self.task)


def install_keyword_api(app, runtime, local_only):
    app.state.keyword_asset_runtime = runtime

    @app.get('/api/v1/voice/keyword-asset', dependencies=[Depends(local_only)])
    async def asset_status():
        return runtime.status()

    @app.post('/api/v1/voice/keyword-asset/prepare', dependencies=[Depends(local_only)])
    async def prepare(payload: KeywordConsent):
        if not payload.confirmed:
            raise HTTPException(400, 'Confirm the signed wake-model download first.')
        return runtime.start()

    @app.post('/api/v1/voice/keyword-asset/repair', dependencies=[Depends(local_only)])
    async def repair(payload: KeywordConsent):
        if not payload.confirmed:
            raise HTTPException(400, 'Confirm the signed wake-model repair first.')
        return runtime.start(repair=True)

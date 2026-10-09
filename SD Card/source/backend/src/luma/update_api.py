"""Local-only GitHub update review and explicit installation endpoints."""
from __future__ import annotations

import asyncio
import base64
from importlib.metadata import version as package_version
import secrets
from datetime import UTC, datetime
from time import monotonic

from fastapi import Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from .github_updates import GitHubUpdateError, latest_release
from .update_agent import UpdateError
from .update_broker import update_request


class InstallRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    candidate_id: str = Field(pattern=r"^[A-Za-z0-9_-]{32,64}$")


def install_update_api(app, local_only):
    candidate = None
    candidate_lock = asyncio.Lock()

    @app.get("/api/v1/updates/status", dependencies=[Depends(local_only)])
    async def update_status():
        try:
            broker = await update_request({"action": "status"})
        except UpdateError as error:
            raise HTTPException(503, str(error)) from None
        app.state.luma.presence_update_busy = broker.get('state') == 'installing'
        return JSONResponse({"current_version": package_version("luma-smart-screen"), **broker},
                            headers={"Cache-Control": "no-store"})

    @app.post("/api/v1/updates/check", dependencies=[Depends(local_only)])
    async def check_updates():
        nonlocal candidate
        current = package_version("luma-smart-screen")
        try:
            release = await asyncio.to_thread(latest_release, current)
        except GitHubUpdateError as error:
            raise HTTPException(503, str(error)) from None
        if release["state"] == "current":
            async with candidate_lock:
                candidate = None
            return JSONResponse({"state": "current", "current_version": current},
                                headers={"Cache-Control": "no-store"})
        candidate_id = secrets.token_urlsafe(32)
        async with candidate_lock:
            candidate = {**release, "candidate_id": candidate_id,
                         "expires": monotonic() + 600}
        return JSONResponse({key: release[key] for key in (
            "state", "current_version", "version", "release_notes", "published_at", "release_url")
            } | {"candidate_id": candidate_id, "expires_in_seconds": 600},
            headers={"Cache-Control": "no-store"})

    @app.post("/api/v1/updates/install", status_code=202,
              dependencies=[Depends(local_only)])
    async def install_update(payload: InstallRequest, request: Request):
        nonlocal candidate
        async with candidate_lock:
            row = candidate
            if (not row or row["expires"] <= monotonic()
                    or not secrets.compare_digest(row["candidate_id"], payload.candidate_id)):
                candidate = None
                raise HTTPException(410, "The reviewed update expired. Check GitHub again.")
            bundle = row["bundle"]
            version = row["version"]
        try:
            check = request.scope.get("luma_companion_check")
            if check is not None:
                check()
            admin_check = request.scope.get('luma_admin_check')
            if admin_check is not None:
                admin_check()
            app.state.luma.presence_update_pending += 1
            try:
                app.state.luma._presence_tick(datetime.now(UTC))
                accepted = await update_request({"action": "install",
                                                 "bundle": base64.b64encode(bundle).decode("ascii")})
                if accepted.get('accepted') is True:
                    app.state.luma.presence_update_busy = True
            finally:
                app.state.luma.presence_update_pending -= 1
        except UpdateError as error:
            raise HTTPException(503, str(error)) from None
        if accepted.get("accepted") is not True or accepted.get("version") != version:
            raise HTTPException(503, "The update was not accepted by Luma's protected installer.")
        async with candidate_lock:
            candidate = None
        return JSONResponse({"accepted": True, "version": version,
                             "message": "The signed update is installing. Luma will briefly restart."},
                            status_code=202, headers={"Cache-Control": "no-store"})

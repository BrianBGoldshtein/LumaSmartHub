"""Local-owner API for encrypted USB export and deliberate restore."""
from __future__ import annotations

import asyncio
import base64
import json
from time import monotonic
import secrets

from fastapi import Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .backup_broker import backup_request
from .admin_authority import require_request_admin
from .countdowns import Countdowns
from .portable_backup import MAX_PASSPHRASE_CHARS, PortableBackupError, apply_document, decrypt, encrypt, snapshot
from .scenes import Scenes
from .transit import Transit


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ExportRequest(StrictModel):
    volume_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    passphrase: str = Field(min_length=12, max_length=MAX_PASSPHRASE_CHARS)
    confirm_passphrase: str = Field(min_length=12, max_length=MAX_PASSPHRASE_CHARS)
    games: dict[str, object] = Field(default_factory=dict)

    @field_validator("games")
    @classmethod
    def bounded_games(cls, value):
        try:
            if len(value) > 4 or len(json.dumps(value, separators=(",", ":"), allow_nan=False)) > 100_000:
                raise ValueError()
        except (TypeError, ValueError, OverflowError):
            raise ValueError("Saved games are too large or invalid to back up.") from None
        return value


class PreviewRequest(StrictModel):
    volume_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    backup_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    passphrase: str = Field(min_length=12, max_length=MAX_PASSPHRASE_CHARS)


class ApplyRequest(StrictModel):
    preview_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    confirmed: bool = Field(strict=True)


class EjectRequest(StrictModel):
    volume_id: str = Field(pattern=r"^[a-f0-9]{32}$")


def install_backup_api(app, service, storage, local_only):
    """Install a local-only API; passphrases and decrypted documents are volatile."""
    previews: dict[str, tuple[float, dict]] = {}
    restore_lock = asyncio.Lock()
    app.state.backup_restore_lock = restore_lock

    def owner():
        require_request_admin()
        if service.settings.onboarding_completed and service.snapshot()["privacy_redacted"]:
            raise HTTPException(403, "Unlock Luma before changing portable settings.")

    async def run_broker(action, **fields):
        try:
            return await backup_request({"action": action, **fields})
        except ValueError as exc:
            raise HTTPException(503, str(exc)) from None

    def trim_previews():
        now = monotonic()
        for key, (expires, _) in list(previews.items()):
            if expires <= now:
                previews.pop(key, None)
        while len(previews) > 3:
            previews.pop(next(iter(previews)))

    @app.post("/api/v1/backups/scan", dependencies=[Depends(local_only)])
    async def scan_media():
        owner()
        result = await run_broker("scan")
        owner()
        return JSONResponse(result, headers={"Cache-Control": "no-store"})

    @app.get("/api/v1/backups/media", dependencies=[Depends(local_only)])
    async def list_media():
        owner()
        result = await run_broker("list")
        owner()
        return JSONResponse(result, headers={"Cache-Control": "no-store"})

    @app.post("/api/v1/backups/export", dependencies=[Depends(local_only)])
    async def export(payload: ExportRequest):
        owner()
        if payload.passphrase != payload.confirm_passphrase:
            raise HTTPException(422, "The two passphrases do not match.")
        try:
            document = snapshot(storage, games=payload.games)
            archive = await asyncio.to_thread(encrypt, document, payload.passphrase)
        except (PortableBackupError, ValueError) as exc:
            raise HTTPException(422, str(exc)) from None
        # Never retain the passphrase/archive in API state or log it. The broker
        # only receives authenticated encrypted bytes; only safe receipt fields
        # are returned to the screen.
        owner()
        result = await run_broker("write", volume_id=payload.volume_id,
                                  archive=base64.b64encode(archive).decode("ascii"))
        if result.get("verified") is not True:
            raise HTTPException(503, "Luma could not verify the saved backup.")
        return JSONResponse({"verified": True, "created_at": result.get("created_at")},
                            headers={"Cache-Control": "no-store"})

    @app.post("/api/v1/backups/preview", dependencies=[Depends(local_only)])
    async def preview(payload: PreviewRequest):
        owner()
        result = await run_broker("read", volume_id=payload.volume_id, backup_id=payload.backup_id)
        try:
            archive = base64.b64decode(result["archive"], validate=True)
            document = await asyncio.to_thread(decrypt, archive, payload.passphrase)
        except (PortableBackupError, ValueError, KeyError, TypeError):
            raise HTTPException(422, "That backup could not be opened. Check the passphrase and try again.") from None
        owner()
        trim_previews()
        preview_id = secrets.token_hex(16)
        previews[preview_id] = (monotonic() + 300, document)
        settings = document["settings"]
        counts = {"countdowns": len(document["countdowns"]),
                  "transit_favorites": len(document["transit_favorites"]),
                  "scene_intents": sum(len(item["actions"]) for item in document["scenes"].values()),
                  "game_checkpoints": len(document["games"])}
        return JSONResponse({
            "preview_id": preview_id,
            "expires_in_seconds": 300,
            "created_at": document["created_at"],
            "theme": settings["theme"],
            "orientation": settings["orientation"],
            "counts": counts,
            "preserved_here": ["Google account and calendar links", "phone pairing", "PIN and privacy state",
                               "purifier binding and credentials", "this Pi's current microphone mute"],
            "requires_review": ["Google and phone links are not transferred", "restored scenes stay off until rebound",
                                "saved game runs in this backup replace the same games on this hub"],
        }, headers={"Cache-Control": "no-store"})

    @app.post("/api/v1/backups/apply", dependencies=[Depends(local_only)])
    async def apply(payload: ApplyRequest):
        owner()
        if not payload.confirmed:
            raise HTTPException(422, "Confirm the restore after reviewing its contents.")
        trim_previews()
        preview_row = previews.get(payload.preview_id)
        if not preview_row or preview_row[0] <= monotonic():
            previews.pop(payload.preview_id, None)
            raise HTTPException(410, "The restore preview expired. Open the backup and review it again.")
        document = preview_row[1]
        async with restore_lock:
            countdown_runtime = app.state.countdown_runtime
            transit_runtime = app.state.transit_runtime
            async with countdown_runtime.refresh_lock:
                async with transit_runtime.lock:
                    scene_runtime = app.state.scene_runtime
                    owner()
                    await scene_runtime.executor.cancel()
                    owner()
                    try:
                        settings = apply_document(storage, document, current=service.settings)
                    except (PortableBackupError, ValueError):
                        raise HTTPException(422, "The reviewed settings could not be applied. Nothing further was changed.") from None
                    service.machine.settings = settings
                    # Keep runtime/store references and the scene lock stable
                    # while installing already-validated persisted records.
                    service.countdowns.__dict__.update(Countdowns(storage).__dict__)
                    service.transit.__dict__.update(Transit(storage).__dict__)
                    scenes = Scenes(storage)
                    with service.scenes.lock:
                        scenes.lock = service.scenes.lock
                        service.scenes.__dict__.update(scenes.__dict__)
                    transit_runtime.store = service.transit
                    scene_runtime.trigger = None
                    scene_runtime.job = None
                    scene_runtime.observed_revision = None
                    scene_runtime.presence.reset()
                    scene_runtime.calendar.reset()
                    countdown_runtime.next_refresh = 0
                    service.tick()
        previews.pop(payload.preview_id, None)
        return JSONResponse({"applied": True, "privacy_redacted": service.snapshot()["privacy_redacted"],
                             "games": document["games"]},
                            headers={"Cache-Control": "no-store"})

    @app.post("/api/v1/backups/eject", dependencies=[Depends(local_only)])
    async def eject(payload: EjectRequest):
        owner()
        result = await run_broker("eject", volume_id=payload.volume_id)
        return JSONResponse(result, headers={"Cache-Control": "no-store"})

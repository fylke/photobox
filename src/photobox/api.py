import base64
import os
import time
from importlib.resources import files
from io import BytesIO
from pathlib import Path
from threading import Lock
from urllib.parse import urlsplit

import qrcode
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from photobox.camera import Camera, MockCamera, camera_from_environment
from photobox.pairing import (
    IssuedCredential,
    PairingError,
    PairingManager,
    PairingRateLimited,
    Principal,
)
from photobox.provision import load_device_config
from photobox.session import InvalidTransition, SessionConflict, SessionManager
from photobox.storage import LocalStorage

_COOKIE_NAME = "photobox_credential"
_CONTROLLER_IDLE_SECONDS = 60


class StartSessionRequest(BaseModel):
    shots: int = Field(default=4, ge=1, le=8)
    countdown_seconds: int = Field(default=3, ge=0, le=10)


class ClaimRequest(BaseModel):
    pin: str = Field(min_length=10, max_length=10, pattern=r"^[0-9]{10}$")


class RedeemInvitationRequest(BaseModel):
    invitation: str = Field(min_length=20, max_length=128)


def create_app(
    camera: Camera | None = None,
    storage_dir: Path | None = None,
    setup_pin_hash: str | None = None,
    device_config_path: Path | None = None,
) -> FastAPI:
    app = FastAPI(title="Photobox", version="0.1.0")
    if setup_pin_hash is not None and device_config_path is not None:
        raise ValueError("Choose either setup_pin_hash or device_config_path, not both")
    device_config = load_device_config(device_config_path) if device_config_path else None
    if device_config is not None:
        setup_pin_hash = str(device_config["setup_pin_hash"])
    data_dir = storage_dir or Path(os.environ.get("PHOTOBOX_DATA_DIR", "~/photobox"))
    storage = LocalStorage(data_dir)
    manager = SessionManager(camera if camera is not None else MockCamera(), storage)
    pairing = PairingManager(storage.root / "pairing.sqlite3", setup_pin_hash)
    app.state.session_manager = manager
    app.state.pairing_manager = pairing
    app.state.device_config = device_config
    screen_html = files("photobox").joinpath("static", "index.html").read_text(encoding="utf-8")
    controller_lock = Lock()
    controller_credential_id: str | None = None
    controller_last_active = 0.0

    def require_principal(request: Request) -> Principal:
        token = request.cookies.get(_COOKIE_NAME)
        if token is None:
            raise HTTPException(status_code=401, detail="Pair this device to continue")
        try:
            return pairing.authenticate(token)
        except PairingError as error:
            raise HTTPException(status_code=401, detail=str(error)) from error

    def require_admin(request: Request) -> tuple[Principal, str]:
        principal = require_principal(request)
        if principal.role != "admin":
            raise HTTPException(status_code=403, detail="Administrator access required")
        return principal, request.cookies[_COOKIE_NAME]

    def validate_origin(request: Request) -> None:
        origin = request.headers.get("origin")
        if origin is None:
            return
        parsed_origin = urlsplit(origin)
        expected = urlsplit(str(request.base_url))
        if (parsed_origin.scheme, parsed_origin.netloc) != (expected.scheme, expected.netloc):
            raise HTTPException(status_code=403, detail="Request origin is not allowed")

    def set_credential_cookie(response: JSONResponse, credential: IssuedCredential, request: Request):
        cookie_options: dict[str, object] = {
            "key": _COOKIE_NAME,
            "value": credential.token,
            "httponly": True,
            "secure": request.url.scheme == "https",
            "samesite": "strict",
            "path": "/",
        }
        if credential.expires_at is not None:
            cookie_options["max_age"] = max(0, credential.expires_at - int(time.time()))
        response.set_cookie(**cookie_options)

    def require_controller(principal: Principal, session_id: str) -> None:
        nonlocal controller_credential_id, controller_last_active
        now = time.monotonic()
        with controller_lock:
            if controller_credential_id is None:
                controller_credential_id = principal.credential_id
            elif controller_credential_id != principal.credential_id:
                if now - controller_last_active < _CONTROLLER_IDLE_SECONDS:
                    raise HTTPException(
                        status_code=409,
                        detail="Session is controlled by another phone",
                    )
                controller_credential_id = principal.credential_id
            controller_last_active = now

    def session_payload(session, principal: Principal) -> dict[str, object]:
        payload = session.to_dict()
        with controller_lock:
            is_controller = controller_credential_id == principal.credential_id
            payload["is_controller"] = is_controller
            payload["can_control"] = (
                controller_credential_id is None
                or is_controller
                or time.monotonic() - controller_last_active >= _CONTROLLER_IDLE_SECONDS
            )
        return payload

    @app.get("/api/pairing/status")
    def pairing_status() -> dict[str, bool]:
        return pairing.status()

    @app.post("/api/pairing/claim")
    def claim_admin(payload: ClaimRequest, request: Request) -> JSONResponse:
        validate_origin(request)
        try:
            credential = pairing.claim_admin(
                payload.pin,
                client_key=request.client.host if request.client is not None else "unknown",
            )
        except PairingRateLimited as error:
            raise HTTPException(status_code=429, detail=str(error)) from error
        except PairingError as error:
            raise HTTPException(status_code=401, detail=str(error)) from error
        response = JSONResponse({"role": credential.role})
        set_credential_cookie(response, credential, request)
        return response

    @app.post("/api/pairing/invitations", status_code=201)
    def create_invitation(request: Request) -> dict[str, object]:
        validate_origin(request)
        _, admin_token = require_admin(request)
        try:
            invitation = pairing.create_invitation(admin_token)
        except PairingError as error:
            raise HTTPException(status_code=401, detail=str(error)) from error
        invitation_url = f"{str(request.base_url).rstrip('/')}/#/invite/{invitation}"
        qr_image = qrcode.make(invitation_url)
        qr_buffer = BytesIO()
        qr_image.save(qr_buffer, format="PNG")
        qr_data_url = "data:image/png;base64," + base64.b64encode(qr_buffer.getvalue()).decode(
            "ascii"
        )
        return {
            "url": invitation_url,
            "qr_data_url": qr_data_url,
            "expires_in_seconds": 600,
        }

    @app.post("/api/pairing/redeem")
    def redeem_invitation(payload: RedeemInvitationRequest, request: Request) -> JSONResponse:
        validate_origin(request)
        try:
            credential = pairing.redeem_invitation(payload.invitation)
        except PairingError as error:
            raise HTTPException(status_code=401, detail=str(error)) from error
        response = JSONResponse({"role": credential.role})
        set_credential_cookie(response, credential, request)
        return response

    @app.get("/api/pairing/me")
    def pairing_me(request: Request) -> dict[str, str]:
        principal = require_principal(request)
        return {"role": principal.role, "credential_id": principal.credential_id}

    @app.get("/api/pairing/guests")
    def list_guests(request: Request) -> list[dict[str, int | str | bool | None]]:
        _, admin_token = require_admin(request)
        try:
            return pairing.list_guests(admin_token)
        except PairingError as error:
            raise HTTPException(status_code=401, detail=str(error)) from error

    @app.delete("/api/pairing/credentials/{credential_id}", status_code=204)
    def revoke_credential(credential_id: str, request: Request) -> None:
        validate_origin(request)
        _, admin_token = require_admin(request)
        try:
            pairing.revoke_credential(admin_token, credential_id)
        except PairingError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    def screen() -> HTMLResponse:
        return HTMLResponse(screen_html)

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "camera": manager.camera.camera_id}

    @app.get("/api/preview")
    def preview(request: Request) -> StreamingResponse:
        require_principal(request)
        frames = manager.camera.iter_preview_frames()

        def stream_frames():
            try:
                for frame in frames:
                    yield (
                        b"--frame\r\n"
                        b"Content-Type: image/jpeg\r\n"
                        + f"Content-Length: {len(frame)}\r\n\r\n".encode("ascii")
                        + frame
                        + b"\r\n"
                    )
            finally:
                close = getattr(frames, "close", None)
                if close is not None:
                    close()

        return StreamingResponse(
            stream_frames(),
            media_type="multipart/x-mixed-replace; boundary=frame",
            headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
        )

    @app.get("/api/session")
    def get_session(request: Request) -> dict[str, object] | None:
        require_principal(request)
        if manager.current is None:
            return None
        return session_payload(manager.current, require_principal(request))

    @app.post("/api/sessions", status_code=201)
    def start_session(payload: StartSessionRequest, request: Request) -> dict[str, object]:
        validate_origin(request)
        principal = require_principal(request)
        with controller_lock:
            try:
                session = manager.start(payload.shots, payload.countdown_seconds)
            except SessionConflict as error:
                raise HTTPException(status_code=409, detail=str(error)) from error
            except ValueError as error:
                raise HTTPException(status_code=422, detail=str(error)) from error
            nonlocal controller_credential_id, controller_last_active
            controller_credential_id = principal.credential_id
            controller_last_active = time.monotonic()
        return session_payload(session, principal)

    @app.post("/api/sessions/{session_id}/advance")
    def advance_session(session_id: str, request: Request) -> dict[str, object]:
        validate_origin(request)
        principal = require_principal(request)
        require_controller(principal, session_id)
        try:
            session = manager.advance(session_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except InvalidTransition as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        except RuntimeError as error:
            raise HTTPException(status_code=503, detail=str(error)) from error
        return session_payload(session, principal)

    @app.post("/api/sessions/{session_id}/control")
    def claim_session_control(session_id: str, request: Request) -> dict[str, object]:
        validate_origin(request)
        principal = require_principal(request)
        if manager.current is None or manager.current.id != session_id:
            raise HTTPException(status_code=404, detail="Session not found")
        require_controller(principal, session_id)
        return session_payload(manager.current, principal)

    @app.get("/api/sessions/{session_id}/photos/{photo_id}")
    def get_photo(
        session_id: str,
        photo_id: str,
        request: Request,
        download: bool = True,
    ) -> FileResponse:
        principal = require_principal(request)
        if manager.current is None or manager.current.id != session_id:
            raise HTTPException(status_code=404, detail="Photo not found")
        if download:
            with controller_lock:
                if controller_credential_id != principal.credential_id:
                    raise HTTPException(status_code=403, detail="Only the session controller can download")
        path = manager.storage.photo_path(session_id, photo_id)
        if path is None:
            raise HTTPException(status_code=404, detail="Photo not found")
        return FileResponse(path, filename=path.name if download else None)

    return app


app = create_app(
    camera=camera_from_environment(),
    setup_pin_hash=os.environ.get("PHOTOBOX_SETUP_PIN_HASH"),
    device_config_path=(
        Path(os.environ["PHOTOBOX_DEVICE_CONFIG"])
        if os.environ.get("PHOTOBOX_DEVICE_CONFIG")
        else None
    ),
)
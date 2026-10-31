import base64
import json
import os
import time
from importlib.resources import files
from io import BytesIO
from pathlib import Path
from threading import Lock
from typing import Literal
from urllib.parse import urlsplit

import qrcode
from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from photobox.camera import Camera, MockCamera, UnavailableCamera
from photobox.camera_registry import CameraRegistry, camera_registry_from_environment
from photobox.network import (
    DisabledNetworkManager,
    NetworkError,
    NetworkManager,
    NetworkManagerAdapter,
)
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


class ConfigureVenueRequest(BaseModel):
    ssid: str = Field(min_length=1, max_length=32)
    password: str = Field(min_length=8, max_length=64)


class ConfigureCamerasRequest(BaseModel):
    roles: dict[str, list[Literal["preview", "capture"]]]
    bindings: dict[str, list[str]]


def create_app(
    camera: Camera | None = None,
    storage_dir: Path | None = None,
    setup_pin_hash: str | None = None,
    device_config_path: Path | None = None,
    network_manager: NetworkManager | None = None,
    camera_registry: CameraRegistry | None = None,
    strip_overlay_path: Path | None = None,
) -> FastAPI:
    app = FastAPI(title="Photobox", version="0.1.0")
    if setup_pin_hash is not None and device_config_path is not None:
        raise ValueError("Choose either setup_pin_hash or device_config_path, not both")
    if camera is not None and camera_registry is not None:
        raise ValueError("Choose either camera or camera_registry, not both")
    registry = camera_registry or CameraRegistry([camera if camera is not None else MockCamera()])
    device_config = load_device_config(device_config_path) if device_config_path else None
    if device_config is not None:
        setup_pin_hash = str(device_config["setup_pin_hash"])
    data_dir = storage_dir or Path(os.environ.get("PHOTOBOX_DATA_DIR", "~/photobox"))
    storage = LocalStorage(data_dir, strip_overlay_path)
    camera_config_path = storage.root / "camera.json"
    if camera_config_path.is_symlink():
        raise RuntimeError("Camera configuration must not be a symlink.")
    if camera_config_path.exists():
        try:
            camera_config = json.loads(camera_config_path.read_text(encoding="utf-8"))
            if not isinstance(camera_config, dict):
                raise TypeError("Camera configuration must be an object.")
            registry.configure(
                {camera_id: set(roles) for camera_id, roles in camera_config["roles"].items()},
                {
                    client_id: tuple(camera_ids)
                    for client_id, camera_ids in camera_config["bindings"].items()
                },
            )
        except (
            OSError,
            AttributeError,
            KeyError,
            TypeError,
            ValueError,
            json.JSONDecodeError,
        ) as error:
            raise RuntimeError(f"Could not load camera configuration: {error}") from error
    capture_camera = (
        registry.camera_for_role("capture", available_only=False) or UnavailableCamera()
    )
    manager = SessionManager(capture_camera, storage)
    pairing = PairingManager(storage.root / "pairing.sqlite3", setup_pin_hash)
    if network_manager is not None:
        network = network_manager
    elif (
        device_config is not None
        and isinstance(device_config.get("wifi"), dict)
        and device_config["wifi"].get("country") is not None
    ):
        network = NetworkManagerAdapter()
    else:
        network = DisabledNetworkManager()
    app.state.session_manager = manager
    app.state.pairing_manager = pairing
    app.state.device_config = device_config
    app.state.camera_registry = registry
    app.router.on_startup.append(registry.start_monitor)
    app.router.on_shutdown.append(registry.stop_monitor)
    screen_html = files("photobox").joinpath("static", "index.html").read_text(encoding="utf-8")
    controller_lock = Lock()
    gif_lock = Lock()
    camera_config_lock = Lock()
    gif_jobs: set[str] = set()
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

    def set_credential_cookie(
        response: JSONResponse, credential: IssuedCredential, request: Request
    ):
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

    @app.get("/api/network/status")
    def network_status() -> dict[str, bool | str | None]:
        return network.status().as_dict()

    @app.post("/api/network/venue")
    def configure_venue_network(
        payload: ConfigureVenueRequest, request: Request
    ) -> dict[str, bool | str | None]:
        validate_origin(request)
        require_admin(request)
        try:
            return network.configure_venue(payload.ssid, payload.password).as_dict()
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        except NetworkError as error:
            raise HTTPException(status_code=503, detail=str(error)) from error

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
        capture_camera = registry.camera_for_role("capture") or UnavailableCamera()
        return {"status": "ok", "camera": capture_camera.camera_id}

    @app.get("/api/cameras")
    def camera_status() -> list[dict[str, object]]:
        return [descriptor.as_dict() for descriptor in registry.descriptors()]

    @app.get("/api/cameras/config")
    def get_camera_configuration(request: Request) -> dict[str, dict[str, list[str]]]:
        require_admin(request)
        return registry.configuration()

    @app.put("/api/cameras/config")
    def configure_cameras(
        payload: ConfigureCamerasRequest,
        request: Request,
    ) -> dict[str, dict[str, list[str]]]:
        validate_origin(request)
        require_admin(request)
        with camera_config_lock:
            try:
                candidate = registry.with_configuration(
                    {camera_id: set(roles) for camera_id, roles in payload.roles.items()},
                    {
                        client_id: tuple(camera_ids)
                        for client_id, camera_ids in payload.bindings.items()
                    },
                )
            except ValueError as error:
                raise HTTPException(status_code=422, detail=str(error)) from error
            configuration = candidate.configuration()
            temporary_path = camera_config_path.with_suffix(".json.tmp")
            try:
                camera_config_path.parent.mkdir(parents=True, exist_ok=True)
                temporary_path.write_text(
                    json.dumps(configuration, indent=2) + "\n",
                    encoding="utf-8",
                )
                temporary_path.replace(camera_config_path)
            except OSError as error:
                temporary_path.unlink(missing_ok=True)
                raise HTTPException(
                    status_code=500,
                    detail=f"Could not persist camera configuration: {error}",
                ) from error
            registry.configure(
                {camera_id: set(roles) for camera_id, roles in payload.roles.items()},
                {
                    client_id: tuple(camera_ids)
                    for client_id, camera_ids in payload.bindings.items()
                },
            )
            manager.camera = (
                registry.camera_for_role("capture", available_only=False) or UnavailableCamera()
            )
            return configuration

    @app.get("/api/preview")
    def preview(request: Request) -> StreamingResponse:
        principal = require_principal(request)
        preview_camera = registry.camera_for_role("preview", principal.credential_id)
        if preview_camera is None or not preview_camera.capabilities().preview:
            raise HTTPException(status_code=503, detail="No camera preview is currently available.")
        frames = preview_camera.iter_preview_frames()

        def stream_frames():
            try:
                for frame in frames:
                    if len(frame) <= 5_000_000:
                        registry.record_preview_frame(preview_camera.camera_id, frame)
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
        capture_camera = registry.camera_for_role("capture", principal.credential_id)
        if capture_camera is None or not capture_camera.capabilities().still_capture:
            raise HTTPException(status_code=503, detail="No still camera is currently available.")
        with controller_lock:
            try:
                session = manager.start(
                    payload.shots,
                    payload.countdown_seconds,
                    capture_camera,
                    preview_frame_provider=lambda: registry.latest_preview_frame(
                        principal.credential_id
                    ),
                    fallback_camera_provider=lambda failed_camera_ids: registry.camera_for_role(
                        "capture",
                        principal.credential_id,
                        exclude_camera_ids=failed_camera_ids,
                    ),
                )
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
        persisted_session = manager.storage.read_session(session_id)
        is_current = manager.current is not None and manager.current.id == session_id
        if persisted_session is None and not is_current:
            raise HTTPException(status_code=404, detail="Photo not found")
        session_record = (
            persisted_session if persisted_session is not None else manager.current.to_dict()
        )
        if photo_id not in session_record.get("photo_ids", []):
            raise HTTPException(status_code=404, detail="Photo not found")
        if download and is_current and persisted_session is None:
            with controller_lock:
                if controller_credential_id != principal.credential_id:
                    raise HTTPException(
                        status_code=403,
                        detail="Only the session controller can download during capture.",
                    )
        path = manager.storage.photo_path(session_id, photo_id)
        if path is None:
            raise HTTPException(status_code=404, detail="Photo not found")
        return FileResponse(path, filename=path.name if download else None)

    @app.get("/api/sessions/{session_id}/gallery")
    def get_gallery(session_id: str, request: Request) -> dict[str, object]:
        require_principal(request)
        session = manager.storage.read_session(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="Gallery not found")
        photos = manager.storage.list_photos(session_id)
        strip_path = manager.storage.composed_path(session_id)
        media = manager.storage.read_media_metadata(session_id)
        animation_status = media.get("animation_status")
        gallery_url = f"{str(request.base_url).rstrip('/')}/#/gallery/{session_id}"
        qr_image = qrcode.make(gallery_url)
        qr_buffer = BytesIO()
        qr_image.save(qr_buffer, format="PNG")
        qr_data_url = "data:image/png;base64," + base64.b64encode(qr_buffer.getvalue()).decode(
            "ascii"
        )
        return {
            "session_id": session_id,
            "photos": [
                {
                    "photo_id": photo["photo_id"],
                    "url": f"/api/sessions/{session_id}/photos/{photo['photo_id']}",
                }
                for photo in photos
            ],
            "strip_url": (
                f"/api/sessions/{session_id}/media/strip" if strip_path is not None else None
            ),
            "gif_status": (
                "ready"
                if manager.storage.animated_path(session_id) is not None
                else (
                    animation_status.get("status", "not_requested")
                    if isinstance(animation_status, dict)
                    else "not_requested"
                )
            ),
            "gif_url": (
                f"/api/sessions/{session_id}/media/gif"
                if manager.storage.animated_path(session_id) is not None
                else None
            ),
            "gif_error": (
                animation_status.get("error")
                if isinstance(animation_status, dict) and animation_status.get("status") == "failed"
                else None
            ),
            "gif_source": (
                media["animation"].get("source")
                if isinstance(media.get("animation"), dict)
                else None
            ),
            "url": gallery_url,
            "qr_data_url": qr_data_url,
        }

    @app.post("/api/sessions/{session_id}/media/gif")
    def create_session_gif(
        session_id: str,
        request: Request,
        background_tasks: BackgroundTasks,
    ) -> JSONResponse:
        principal = require_principal(request)
        session = manager.storage.read_session(session_id)
        if session is None or session.get("state") != "done":
            raise HTTPException(status_code=404, detail="Completed session not found")
        preview_frames = registry.recent_preview_frames(principal.credential_id)
        photo_ids = session.get("photo_ids")
        if not isinstance(photo_ids, list) or not all(
            isinstance(photo_id, str) for photo_id in photo_ids
        ):
            raise HTTPException(status_code=422, detail="Session has invalid photo metadata.")
        if len(preview_frames) < 2 and len(photo_ids) < 2:
            raise HTTPException(
                status_code=422,
                detail="At least two captured photos are needed to create a GIF.",
            )
        if len(preview_frames) < 2 and len(photo_ids) > 8:
            raise HTTPException(status_code=422, detail="Session exceeds the GIF frame limit.")

        with gif_lock:
            if manager.storage.animated_path(session_id) is not None:
                return JSONResponse(
                    {"status": "ready", "url": f"/api/sessions/{session_id}/media/gif"}
                )
            if session_id in gif_jobs:
                raise HTTPException(status_code=409, detail="GIF creation is already in progress.")
            manager.storage.update_media_metadata(
                session_id,
                {"animation_status": {"status": "processing"}},
            )
            gif_jobs.add(session_id)

        def encode_gif() -> None:
            try:
                if len(preview_frames) >= 2:
                    manager.storage.compose_gif_from_preview(session_id, preview_frames)
                else:
                    manager.storage.compose_gif(session_id, photo_ids)
            except (OSError, RuntimeError, ValueError) as error:
                manager.storage.update_media_metadata(
                    session_id,
                    {"animation_status": {"status": "failed", "error": str(error)}},
                )
            else:
                manager.storage.update_media_metadata(
                    session_id,
                    {"animation_status": {"status": "ready"}},
                )
            finally:
                with gif_lock:
                    gif_jobs.discard(session_id)

        background_tasks.add_task(encode_gif)
        return JSONResponse({"status": "processing"}, status_code=202)

    @app.get("/api/sessions/{session_id}/media/strip")
    def get_composed_strip(session_id: str, request: Request) -> FileResponse:
        require_principal(request)
        session = manager.storage.read_session(session_id)
        path = manager.storage.composed_path(session_id)
        if session is None or path is None:
            raise HTTPException(status_code=404, detail="Composed strip not found")
        return FileResponse(path, filename=path.name, media_type="image/jpeg")

    @app.get("/api/sessions/{session_id}/media/gif")
    def get_animated_gif(session_id: str, request: Request) -> FileResponse:
        require_principal(request)
        session = manager.storage.read_session(session_id)
        path = manager.storage.animated_path(session_id)
        if session is None or path is None:
            raise HTTPException(status_code=404, detail="Animated GIF not found")
        return FileResponse(path, filename=path.name, media_type="image/gif")

    return app


app = create_app(
    camera_registry=camera_registry_from_environment(),
    setup_pin_hash=os.environ.get("PHOTOBOX_SETUP_PIN_HASH"),
    device_config_path=(
        Path(os.environ["PHOTOBOX_DEVICE_CONFIG"])
        if os.environ.get("PHOTOBOX_DEVICE_CONFIG")
        else None
    ),
    strip_overlay_path=(
        Path(os.environ["PHOTOBOX_STRIP_OVERLAY"])
        if os.environ.get("PHOTOBOX_STRIP_OVERLAY")
        else None
    ),
)

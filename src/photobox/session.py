from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from uuid import uuid4

from photobox.camera import Camera, CapturedImage
from photobox.storage import LocalStorage


class SessionState(StrEnum):
    ARMED = "armed"
    COUNTDOWN = "countdown"
    CAPTURING = "capturing"
    REVIEW = "review"
    COMPOSING = "composing"
    DONE = "done"


class SessionConflict(Exception):
    pass


class InvalidTransition(Exception):
    pass


@dataclass
class CaptureSession:
    id: str
    state: SessionState
    shots_total: int
    countdown_seconds: int
    started_at: str
    camera_id: str
    shots_taken: int = 0
    camera_fallback: bool = False
    photo_ids: list[str] = field(default_factory=list)
    low_quality_photo_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        session = asdict(self)
        session["state"] = self.state.value
        return session


class SessionManager:
    def __init__(self, camera: Camera, storage: LocalStorage):
        self.camera = camera
        self._active_camera = camera
        self.storage = storage
        self.current: CaptureSession | None = None

    def start(
        self,
        shots: int,
        countdown_seconds: int,
        camera: Camera | None = None,
        preview_frame_provider: Callable[[], bytes | None] | None = None,
        fallback_camera_provider: Callable[[set[str]], Camera | None] | None = None,
    ) -> CaptureSession:
        if self.current and self.current.state is not SessionState.DONE:
            raise SessionConflict("A session is already in progress")
        if not 1 <= shots <= 8:
            raise ValueError("shots must be between 1 and 8")
        if not 0 <= countdown_seconds <= 10:
            raise ValueError("countdown_seconds must be between 0 and 10")

        self._active_camera = camera or self.camera
        self._preview_frame_provider = preview_frame_provider
        self._fallback_camera_provider = fallback_camera_provider
        self._failed_camera_ids: set[str] = set()
        self.current = CaptureSession(
            id=str(uuid4()),
            state=SessionState.ARMED,
            shots_total=shots,
            countdown_seconds=countdown_seconds,
            started_at=datetime.now(UTC).isoformat(),
            camera_id=self._active_camera.camera_id,
        )
        return self.current

    def advance(self, session_id: str) -> CaptureSession:
        session = self.current
        if session is None or session.id != session_id:
            raise KeyError("Session not found")

        if session.state is SessionState.ARMED:
            session.state = SessionState.COUNTDOWN
        elif session.state is SessionState.COUNTDOWN:
            session.state = SessionState.CAPTURING
        elif session.state is SessionState.CAPTURING:
            captured = self._capture_with_fallback(session)
            photo_id = self.storage.save_photo(session.id, captured)
            session.photo_ids.append(photo_id)
            if captured.low_quality:
                session.low_quality_photo_ids.append(photo_id)
            session.shots_taken += 1
            session.state = SessionState.REVIEW
        elif session.state is SessionState.REVIEW:
            session.state = (
                SessionState.COUNTDOWN
                if session.shots_taken < session.shots_total
                else SessionState.COMPOSING
            )
        elif session.state is SessionState.COMPOSING:
            try:
                self.storage.compose_strip(session.id, session.photo_ids)
            except (OSError, RuntimeError, ValueError) as error:
                raise RuntimeError(f"Could not compose the photo strip: {error}") from error
            session.state = SessionState.DONE
            self.storage.save_session(session.to_dict())
        else:
            raise InvalidTransition("A completed session cannot be advanced")

        return session

    def _capture_with_fallback(self, session: CaptureSession) -> CapturedImage:
        try:
            return self._active_camera.capture_still()
        except RuntimeError as first_error:
            try:
                return self._active_camera.capture_still()
            except RuntimeError as retry_error:
                self._failed_camera_ids.add(self._active_camera.camera_id)
                fallback_error = retry_error
                while self._fallback_camera_provider is not None:
                    fallback_camera = self._fallback_camera_provider(self._failed_camera_ids)
                    if fallback_camera is None:
                        break
                    self._failed_camera_ids.add(fallback_camera.camera_id)
                    try:
                        captured = fallback_camera.capture_still()
                    except RuntimeError as camera_error:
                        fallback_error = camera_error
                        continue
                    self._active_camera = fallback_camera
                    session.camera_id = fallback_camera.camera_id
                    session.camera_fallback = True
                    return captured
                frame = (
                    self._preview_frame_provider()
                    if self._preview_frame_provider is not None
                    else None
                )
                if (
                    frame is not None
                    and len(frame) <= 5_000_000
                    and frame.startswith(b"\xff\xd8")
                    and frame.endswith(b"\xff\xd9")
                ):
                    return CapturedImage(frame, "jpg", "image/jpeg", low_quality=True)
                raise RuntimeError(
                    f"Camera capture failed after one retry and no fallback camera or recent "
                    f"preview frame is available: {fallback_error}"
                ) from first_error

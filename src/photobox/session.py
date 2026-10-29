from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from uuid import uuid4

from photobox.camera import Camera
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
    shots_taken: int = 0
    photo_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        session = asdict(self)
        session["state"] = self.state.value
        return session


class SessionManager:
    def __init__(self, camera: Camera, storage: LocalStorage):
        self.camera = camera
        self.storage = storage
        self.current: CaptureSession | None = None

    def start(self, shots: int, countdown_seconds: int) -> CaptureSession:
        if self.current and self.current.state is not SessionState.DONE:
            raise SessionConflict("A session is already in progress")
        if not 1 <= shots <= 8:
            raise ValueError("shots must be between 1 and 8")
        if not 0 <= countdown_seconds <= 10:
            raise ValueError("countdown_seconds must be between 0 and 10")

        self.current = CaptureSession(
            id=str(uuid4()),
            state=SessionState.ARMED,
            shots_total=shots,
            countdown_seconds=countdown_seconds,
            started_at=datetime.now(UTC).isoformat(),
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
            photo_id = self.storage.save_photo(session.id, self.camera.capture_still())
            session.photo_ids.append(photo_id)
            session.shots_taken += 1
            session.state = SessionState.REVIEW
        elif session.state is SessionState.REVIEW:
            session.state = (
                SessionState.COUNTDOWN
                if session.shots_taken < session.shots_total
                else SessionState.COMPOSING
            )
        elif session.state is SessionState.COMPOSING:
            session.state = SessionState.DONE
            self.storage.save_session(session.to_dict())
        else:
            raise InvalidTransition("A completed session cannot be advanced")

        return session
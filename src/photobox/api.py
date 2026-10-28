import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from photobox.camera import Camera, MockCamera
from photobox.session import InvalidTransition, SessionConflict, SessionManager
from photobox.storage import LocalStorage


class StartSessionRequest(BaseModel):
    shots: int = Field(default=4, ge=1, le=8)
    countdown_seconds: int = Field(default=3, ge=0, le=10)


def create_app(camera: Camera | None = None, storage_dir: Path | None = None) -> FastAPI:
    app = FastAPI(title="Photobox", version="0.1.0")
    data_dir = storage_dir or Path(os.environ.get("PHOTOBOX_DATA_DIR", "~/photobox"))
    manager = SessionManager(camera or MockCamera(), LocalStorage(data_dir))
    app.state.session_manager = manager

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "camera": manager.camera.camera_id}

    @app.get("/api/session")
    def get_session() -> dict[str, object] | None:
        if manager.current is None:
            return None
        return manager.current.to_dict()

    @app.post("/api/sessions", status_code=201)
    def start_session(request: StartSessionRequest) -> dict[str, object]:
        try:
            session = manager.start(request.shots, request.countdown_seconds)
        except SessionConflict as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        return session.to_dict()

    @app.post("/api/sessions/{session_id}/advance")
    def advance_session(session_id: str) -> dict[str, object]:
        try:
            session = manager.advance(session_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except InvalidTransition as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        return session.to_dict()

    @app.get("/api/sessions/{session_id}/photos/{photo_id}")
    def get_photo(session_id: str, photo_id: str) -> FileResponse:
        path = manager.storage.photo_path(session_id, photo_id)
        if path is None:
            raise HTTPException(status_code=404, detail="Photo not found")
        return FileResponse(path, filename=path.name)

    return app


app = create_app()
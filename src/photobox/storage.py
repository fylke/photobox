import json
from pathlib import Path
from uuid import uuid4

from photobox.camera import CapturedImage


class LocalStorage:
    def __init__(self, root: Path):
        self.root = root.expanduser()

    def save_photo(self, session_id: str, image: CapturedImage) -> str:
        session_dir = self.root / "events" / "default" / session_id
        session_dir.mkdir(parents=True, exist_ok=True)
        photo_id = str(uuid4())
        (session_dir / f"{photo_id}.{image.extension}").write_bytes(image.data)
        return photo_id

    def save_session(self, session: dict[str, object]) -> None:
        session_dir = self.root / "events" / "default" / str(session["id"])
        session_dir.mkdir(parents=True, exist_ok=True)
        metadata_path = session_dir / "session.json"
        temporary_path = metadata_path.with_suffix(".json.tmp")
        temporary_path.write_text(json.dumps(session, indent=2) + "\n", encoding="utf-8")
        temporary_path.replace(metadata_path)
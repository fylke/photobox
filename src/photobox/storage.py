import json
from pathlib import Path
from uuid import UUID, uuid4

from PIL import Image, ImageOps

from photobox.camera import CapturedImage

_STRIP_SLOT_SIZE = (360, 480)
_STRIP_PADDING = 24
_MAX_SOURCE_BYTES = 50_000_000
_MAX_SOURCE_PIXELS = 20_000_000
_ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "ppm"}


class LocalStorage:
    def __init__(self, root: Path):
        self.root = root.expanduser()

    def save_photo(self, session_id: str, image: CapturedImage) -> str:
        normalized_id = self._normalize_uuid(session_id)
        if normalized_id is None:
            raise ValueError("Invalid session ID.")
        if image.extension.lower() not in _ALLOWED_EXTENSIONS:
            raise ValueError("Unsupported captured image extension.")
        if len(image.data) > _MAX_SOURCE_BYTES:
            raise ValueError("Captured image exceeds the size limit.")
        session_dir = self._session_dir(normalized_id)
        session_dir.mkdir(parents=True, exist_ok=True)
        photo_id = str(uuid4())
        (session_dir / f"{photo_id}.{image.extension}").write_bytes(image.data)
        if image.low_quality:
            low_quality_ids = self._read_low_quality_ids(normalized_id)
            low_quality_ids.append(photo_id)
            self._write_media_metadata(
                normalized_id,
                {"low_quality_photo_ids": low_quality_ids},
            )
        return photo_id

    def photo_path(self, session_id: str, photo_id: str) -> Path | None:
        normalized_session_id = self._normalize_uuid(session_id)
        normalized_photo_id = self._normalize_uuid(photo_id)
        if normalized_session_id is None or normalized_photo_id is None:
            return None

        session_dir = self._session_dir(normalized_session_id)
        matches = list(session_dir.glob(f"{normalized_photo_id}.*"))
        return matches[0] if matches and matches[0].is_file() else None

    def composed_path(self, session_id: str) -> Path | None:
        normalized_id = self._normalize_uuid(session_id)
        if normalized_id is None:
            return None
        path = self._session_dir(normalized_id) / "strip.jpg"
        return path if path.is_file() else None

    def compose_strip(self, session_id: str, photo_ids: list[str]) -> Path:
        normalized_id = self._normalize_uuid(session_id)
        if normalized_id is None:
            raise ValueError("Invalid session ID.")
        if not 1 <= len(photo_ids) <= 8:
            raise ValueError("A strip must contain between 1 and 8 photos.")

        slot_width, slot_height = _STRIP_SLOT_SIZE
        output = Image.new(
            "RGB",
            (
                slot_width + _STRIP_PADDING * 2,
                len(photo_ids) * slot_height + (len(photo_ids) + 1) * _STRIP_PADDING,
            ),
            "white",
        )
        for index, photo_id in enumerate(photo_ids):
            source_path = self.photo_path(normalized_id, photo_id)
            if source_path is None:
                raise ValueError(f"Original photo {photo_id!r} is missing.")
            if source_path.stat().st_size > _MAX_SOURCE_BYTES:
                raise ValueError(f"Original photo {photo_id!r} exceeds the size limit.")
            try:
                with Image.open(source_path) as source:
                    if source.width * source.height > _MAX_SOURCE_PIXELS:
                        raise ValueError(f"Original photo {photo_id!r} exceeds the pixel limit.")
                    slot = ImageOps.fit(
                        source.convert("RGB"),
                        _STRIP_SLOT_SIZE,
                        method=Image.Resampling.LANCZOS,
                    )
            except (OSError, Image.DecompressionBombError) as error:
                raise ValueError(f"Original photo {photo_id!r} is not a valid image.") from error
            x = _STRIP_PADDING
            y = _STRIP_PADDING + index * (slot_height + _STRIP_PADDING)
            output.paste(slot, (x, y))

        session_dir = self._session_dir(normalized_id)
        session_dir.mkdir(parents=True, exist_ok=True)
        strip_path = session_dir / "strip.jpg"
        temporary_path = session_dir / "strip.jpg.tmp"
        output.save(temporary_path, format="JPEG", quality=90, optimize=True)
        temporary_path.replace(strip_path)
        self._write_media_metadata(
            normalized_id,
            {
                "composition": {
                    "type": "vertical-strip",
                    "file": strip_path.name,
                    "width": output.width,
                    "height": output.height,
                    "photo_ids": list(photo_ids),
                }
            },
        )
        return strip_path

    def list_sessions(self) -> list[dict[str, object]]:
        sessions: list[dict[str, object]] = []
        events_dir = self.root / "events" / "default"
        if not events_dir.is_dir():
            return sessions
        for session_dir in sorted(events_dir.iterdir(), key=lambda path: path.name):
            if not session_dir.is_dir() or self._normalize_uuid(session_dir.name) is None:
                continue
            session = self.read_session(session_dir.name)
            if session is not None:
                sessions.append(session)
        return sessions

    def read_session(self, session_id: str) -> dict[str, object] | None:
        normalized_id = self._normalize_uuid(session_id)
        if normalized_id is None:
            return None
        metadata_path = self._session_dir(normalized_id) / "session.json"
        try:
            session = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return session if isinstance(session, dict) and session.get("id") == normalized_id else None

    def list_photos(self, session_id: str) -> list[dict[str, str]]:
        session = self.read_session(session_id)
        if session is None:
            return []
        photo_ids = session.get("photo_ids")
        if not isinstance(photo_ids, list):
            return []
        photos = []
        for photo_id in photo_ids:
            if not isinstance(photo_id, str):
                continue
            path = self.photo_path(session_id, photo_id)
            if path is not None:
                photos.append({"photo_id": photo_id, "filename": path.name})
        return photos

    def save_session(self, session: dict[str, object]) -> None:
        session_id = self._normalize_uuid(str(session["id"]))
        if session_id is None:
            raise ValueError("Invalid session ID.")
        session_dir = self._session_dir(session_id)
        session_dir.mkdir(parents=True, exist_ok=True)
        metadata_path = session_dir / "session.json"
        temporary_path = metadata_path.with_suffix(".json.tmp")
        temporary_path.write_text(json.dumps(session, indent=2) + "\n", encoding="utf-8")
        temporary_path.replace(metadata_path)

    def read_media_metadata(self, session_id: str) -> dict[str, object]:
        normalized_id = self._normalize_uuid(session_id)
        if normalized_id is None:
            return {}
        metadata_path = self._session_dir(normalized_id) / "media.json"
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}
        except json.JSONDecodeError as error:
            raise RuntimeError(f"Media metadata is corrupted: {metadata_path}") from error
        return metadata if isinstance(metadata, dict) else {}

    def _read_low_quality_ids(self, session_id: str) -> list[str]:
        photo_ids = self.read_media_metadata(session_id).get("low_quality_photo_ids", [])
        return photo_ids if isinstance(photo_ids, list) else []

    def _write_media_metadata(self, session_id: str, updates: dict[str, object]) -> None:
        session_dir = self._session_dir(session_id)
        session_dir.mkdir(parents=True, exist_ok=True)
        metadata = self.read_media_metadata(session_id)
        metadata.update(updates)
        metadata_path = session_dir / "media.json"
        temporary_path = metadata_path.with_suffix(".json.tmp")
        temporary_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
        temporary_path.replace(metadata_path)

    def _session_dir(self, session_id: str) -> Path:
        return self.root / "events" / "default" / session_id

    @staticmethod
    def _normalize_uuid(value: str) -> str | None:
        try:
            return str(UUID(value))
        except ValueError:
            return None

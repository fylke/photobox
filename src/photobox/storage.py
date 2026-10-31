import json
from io import BytesIO
from pathlib import Path
from uuid import UUID, uuid4

from PIL import Image, ImageOps

from photobox.camera import CapturedImage

_STRIP_SLOT_SIZE = (360, 480)
_STRIP_PADDING = 24
_MAX_SOURCE_BYTES = 50_000_000
_MAX_SOURCE_PIXELS = 20_000_000
_MAX_GIF_FRAMES = 8
_MAX_GIF_WIDTH = 640
_MAX_GIF_HEIGHT = 640
_GIF_FRAME_DURATION_MS = 250
_MAX_GIF_BYTES = 10_000_000
_ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "ppm"}


class LocalStorage:
    def __init__(self, root: Path, strip_overlay_path: Path | None = None):
        self.root = root.expanduser()
        self._strip_overlay = (
            self._load_strip_overlay(strip_overlay_path) if strip_overlay_path is not None else None
        )

    def save_photo(self, session_id: str, image: CapturedImage) -> str:
        normalized_id = self._normalize_uuid(session_id)
        if normalized_id is None:
            raise ValueError("Invalid session ID.")
        if image.extension.lower() not in _ALLOWED_EXTENSIONS:
            raise ValueError("Unsupported captured image extension.")
        if len(image.data) > _MAX_SOURCE_BYTES:
            raise ValueError("Captured image exceeds the size limit.")
        session_dir = self._session_dir(session_id)
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

    def animated_path(self, session_id: str) -> Path | None:
        normalized_id = self._normalize_uuid(session_id)
        if normalized_id is None:
            return None
        path = self._session_dir(normalized_id) / "photos.gif"
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
            if self._strip_overlay is not None:
                slot = Image.alpha_composite(slot.convert("RGBA"), self._strip_overlay).convert(
                    "RGB"
                )
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

    def compose_gif(self, session_id: str, photo_ids: list[str]) -> Path:
        normalized_id = self._normalize_uuid(session_id)
        if normalized_id is None:
            raise ValueError("Invalid session ID.")
        if not 2 <= len(photo_ids) <= _MAX_GIF_FRAMES:
            raise ValueError(
                f"An animated GIF must contain between 2 and {_MAX_GIF_FRAMES} photos."
            )

        frames: list[Image.Image] = []
        try:
            for photo_id in photo_ids:
                source_path = self.photo_path(normalized_id, photo_id)
                if source_path is None:
                    raise ValueError(f"Original photo {photo_id!r} is missing.")
                if source_path.stat().st_size > _MAX_SOURCE_BYTES:
                    raise ValueError(f"Original photo {photo_id!r} exceeds the size limit.")
                with Image.open(source_path) as source:
                    if source.width * source.height > _MAX_SOURCE_PIXELS:
                        raise ValueError(f"Original photo {photo_id!r} exceeds the pixel limit.")
                    frame = source.convert("RGB")
                    frame.thumbnail(
                        (_MAX_GIF_WIDTH, _MAX_GIF_HEIGHT),
                        Image.Resampling.LANCZOS,
                    )
                    frames.append(frame)
        except (OSError, Image.DecompressionBombError) as error:
            for frame in frames:
                frame.close()
            raise ValueError(f"Original photo could not be encoded as a GIF: {error}") from error
        except ValueError:
            for frame in frames:
                frame.close()
            raise

        return self._write_gif(
            normalized_id,
            frames,
            photo_ids,
            source="session-photos",
        )

    def compose_gif_from_preview(self, session_id: str, preview_frames: list[bytes]) -> Path:
        normalized_id = self._normalize_uuid(session_id)
        if normalized_id is None:
            raise ValueError("Invalid session ID.")
        if not 2 <= len(preview_frames) <= _MAX_GIF_FRAMES:
            raise ValueError(
                f"An animated GIF must contain between 2 and {_MAX_GIF_FRAMES} preview frames."
            )

        frames: list[Image.Image] = []
        try:
            for frame_data in preview_frames:
                if len(frame_data) > _MAX_SOURCE_BYTES:
                    raise ValueError("Preview frame exceeds the GIF source size limit.")
                if not frame_data.startswith(b"\xff\xd8") or not frame_data.endswith(b"\xff\xd9"):
                    raise ValueError("Preview frame is not a valid JPEG.")
                with Image.open(BytesIO(frame_data)) as source:
                    if source.format != "JPEG":
                        raise ValueError("Preview frame is not a valid JPEG.")
                    if source.width * source.height > _MAX_SOURCE_PIXELS:
                        raise ValueError("Preview frame exceeds the pixel limit.")
                    frame = source.convert("RGB")
                    frame.thumbnail(
                        (_MAX_GIF_WIDTH, _MAX_GIF_HEIGHT),
                        Image.Resampling.LANCZOS,
                    )
                    frames.append(frame)
        except (OSError, Image.DecompressionBombError) as error:
            for frame in frames:
                frame.close()
            raise ValueError(f"Preview frame could not be encoded as a GIF: {error}") from error
        except ValueError:
            for frame in frames:
                frame.close()
            raise

        return self._write_gif(
            normalized_id,
            frames,
            [],
            source="preview",
        )

    def _write_gif(
        self,
        session_id: str,
        frames: list[Image.Image],
        photo_ids: list[str],
        *,
        source: str,
    ) -> Path:
        canvas_size = (
            max(frame.width for frame in frames),
            max(frame.height for frame in frames),
        )
        normalized_frames: list[Image.Image] = []
        for frame in frames:
            canvas = Image.new("RGB", canvas_size, "white")
            canvas.paste(
                frame,
                ((canvas_size[0] - frame.width) // 2, (canvas_size[1] - frame.height) // 2),
            )
            normalized_frames.append(canvas)
            frame.close()
        frames = normalized_frames

        session_dir = self._session_dir(session_id)
        session_dir.mkdir(parents=True, exist_ok=True)
        gif_path = session_dir / "photos.gif"
        temporary_path = session_dir / "photos.gif.tmp"
        try:
            frames[0].save(
                temporary_path,
                format="GIF",
                save_all=True,
                append_images=frames[1:],
                duration=_GIF_FRAME_DURATION_MS,
                loop=0,
                optimize=True,
            )
            if temporary_path.stat().st_size > _MAX_GIF_BYTES:
                raise ValueError("Generated GIF exceeds the 10 MB size limit.")
            temporary_path.replace(gif_path)
        finally:
            for frame in frames:
                frame.close()
            temporary_path.unlink(missing_ok=True)

        self._write_media_metadata(
            session_id,
            {
                "animation": {
                    "type": "animated-gif",
                    "source": source,
                    "file": gif_path.name,
                    "frame_count": len(frames),
                    "frame_duration_ms": _GIF_FRAME_DURATION_MS,
                    "max_width": _MAX_GIF_WIDTH,
                    "width": canvas_size[0],
                    "height": canvas_size[1],
                    "photo_ids": list(photo_ids),
                }
            },
        )
        return gif_path

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

    def update_media_metadata(self, session_id: str, updates: dict[str, object]) -> None:
        normalized_id = self._normalize_uuid(session_id)
        if normalized_id is None:
            raise ValueError("Invalid session ID.")
        self._write_media_metadata(normalized_id, updates)

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
    def _load_strip_overlay(path: Path) -> Image.Image:
        path = path.expanduser()
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"Strip overlay must be a regular local file: {path}")
        if path.stat().st_size > 5_000_000:
            raise ValueError("Strip overlay exceeds the 5 MB size limit.")
        try:
            with Image.open(path) as source:
                if source.format != "PNG":
                    raise ValueError("Strip overlay must be a PNG image.")
                if source.size != _STRIP_SLOT_SIZE:
                    raise ValueError(
                        f"Strip overlay must be {_STRIP_SLOT_SIZE[0]}x{_STRIP_SLOT_SIZE[1]} pixels."
                    )
                if source.mode not in {"RGBA", "LA"} and "transparency" not in source.info:
                    raise ValueError("Strip overlay must include transparent pixels.")
                overlay = source.convert("RGBA")
                if overlay.getchannel("A").getextrema()[0] == 255:
                    raise ValueError("Strip overlay must include transparent pixels.")
                return overlay
        except (OSError, Image.DecompressionBombError) as error:
            raise ValueError(f"Strip overlay is not a valid PNG image: {path}") from error

    @staticmethod
    def _normalize_uuid(value: str) -> str | None:
        try:
            return str(UUID(value))
        except ValueError:
            return None

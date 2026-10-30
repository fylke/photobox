import json
from uuid import uuid4

import pytest
from PIL import Image

from photobox.camera import CapturedImage, MockCamera
from photobox.storage import LocalStorage


def test_strip_composition_preserves_originals_and_records_slot_order(tmp_path):
    storage = LocalStorage(tmp_path)
    session_id = str(uuid4())
    photo_ids = [
        storage.save_photo(
            session_id,
            CapturedImage(
                b"P6\n64 48\n255\n" + bytes([255, 0, 0]) * (64 * 48),
                "ppm",
                "image/x-portable-pixmap",
            ),
        ),
        storage.save_photo(
            session_id,
            CapturedImage(
                b"P6\n64 48\n255\n" + bytes([0, 0, 255]) * (64 * 48),
                "ppm",
                "image/x-portable-pixmap",
            ),
        ),
    ]
    originals = [storage.photo_path(session_id, photo_id).read_bytes() for photo_id in photo_ids]
    storage.save_session(
        {
            "id": session_id,
            "state": "done",
            "photo_ids": photo_ids,
            "shots_taken": 2,
        }
    )

    strip_path = storage.compose_strip(session_id, photo_ids)

    with Image.open(strip_path) as strip:
        assert strip.size == (408, 1032)
        assert strip.getpixel((24 + 180, 24 + 240))[0] > 200
        assert strip.getpixel((24 + 180, 24 + 480 + 24 + 240))[2] > 200
    assert [
        storage.photo_path(session_id, photo_id).read_bytes() for photo_id in photo_ids
    ] == originals
    metadata = storage.read_media_metadata(session_id)
    assert metadata["composition"] == {
        "type": "vertical-strip",
        "file": "strip.jpg",
        "width": 408,
        "height": 1032,
        "photo_ids": photo_ids,
    }
    assert storage.list_sessions()[0]["id"] == session_id
    assert [photo["photo_id"] for photo in storage.list_photos(session_id)] == photo_ids


def test_storage_persists_low_quality_metadata_without_mutating_original(tmp_path):
    storage = LocalStorage(tmp_path)
    session_id = str(uuid4())
    captured = MockCamera().capture_still()
    photo_id = storage.save_photo(
        session_id,
        CapturedImage(captured.data, captured.extension, captured.media_type, low_quality=True),
    )
    storage.save_session({"id": session_id, "state": "done", "photo_ids": [photo_id]})

    assert storage.read_media_metadata(session_id)["low_quality_photo_ids"] == [photo_id]
    assert storage.photo_path(session_id, photo_id).read_bytes() == captured.data


def test_strip_composition_rejects_corrupt_source_without_modifying_it(tmp_path):
    storage = LocalStorage(tmp_path)
    session_id = str(uuid4())
    captured = CapturedImage(b"not an image", "ppm", "image/x-portable-pixmap")
    photo_id = storage.save_photo(session_id, captured)

    with pytest.raises(ValueError, match="not a valid image"):
        storage.compose_strip(session_id, [photo_id])

    assert storage.photo_path(session_id, photo_id).read_bytes() == captured.data
    assert storage.composed_path(session_id) is None


@pytest.mark.parametrize("photo_ids", [[], ["bad"], [str(uuid4())] * 9])
def test_strip_rejects_empty_or_invalid_photo_sets(tmp_path, photo_ids):
    storage = LocalStorage(tmp_path)

    with pytest.raises(ValueError):
        storage.compose_strip(str(uuid4()), photo_ids)


def test_storage_ignores_invalid_session_directories_and_ids(tmp_path):
    storage = LocalStorage(tmp_path)
    events_dir = tmp_path / "events" / "default"
    (events_dir / "not-a-session").mkdir(parents=True)
    session_id = str(uuid4())
    session_dir = events_dir / session_id
    session_dir.mkdir()
    (session_dir / "session.json").write_text(
        json.dumps({"id": session_id, "photo_ids": []}),
        encoding="utf-8",
    )

    assert storage.list_sessions() == [{"id": session_id, "photo_ids": []}]
    assert storage.read_session("../../session.json") is None
    assert storage.photo_path(session_id, "../../session.json") is None

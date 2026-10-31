import json
import tempfile
import unittest
from pathlib import Path

from photobox.camera import MockCamera
from photobox.session import (
    InvalidTransition,
    SessionConflict,
    SessionManager,
    SessionState,
)
from photobox.storage import LocalStorage


class AlternateCamera(MockCamera):
    @property
    def camera_id(self) -> str:
        return "mock-selected"


class FailingCamera(AlternateCamera):
    def __init__(self) -> None:
        self.capture_attempts = 0

    def capture_still(self):
        self.capture_attempts += 1
        raise RuntimeError("DSLR unavailable")


class FallbackCamera(AlternateCamera):
    @property
    def camera_id(self) -> str:
        return "webcam-fallback"


class RecoveringCamera(AlternateCamera):
    def __init__(self) -> None:
        self.capture_attempts = 0

    def capture_still(self):
        self.capture_attempts += 1
        if self.capture_attempts <= 2:
            raise RuntimeError("DSLR disconnected")
        return super().capture_still()


class CountingFallbackCamera(FallbackCamera):
    def __init__(self) -> None:
        self.capture_attempts = 0

    def capture_still(self):
        self.capture_attempts += 1
        return super().capture_still()


class SessionManagerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.storage_dir = Path(self.temp_dir.name)
        self.manager = SessionManager(MockCamera(), LocalStorage(self.storage_dir))

    def test_session_captures_and_persists_metadata(self) -> None:
        session = self.manager.start(shots=1, countdown_seconds=0)
        for _ in range(5):
            session = self.manager.advance(session.id)

        self.assertEqual(session.state, SessionState.DONE)
        self.assertEqual(session.shots_taken, 1)
        self.assertEqual(len(session.photo_ids), 1)

        session_dir = self.storage_dir / "events" / "default" / session.id
        image_path = session_dir / f"{session.photo_ids[0]}.ppm"
        self.assertTrue(image_path.read_bytes().startswith(b"P6\n64 48\n255\n"))
        metadata = json.loads((session_dir / "session.json").read_text(encoding="utf-8"))
        self.assertEqual(metadata["state"], "done")
        self.assertEqual(metadata["photo_ids"], session.photo_ids)

    def test_only_one_session_can_run_at_a_time(self) -> None:
        self.manager.start(shots=1, countdown_seconds=0)
        with self.assertRaises(SessionConflict):
            self.manager.start(shots=1, countdown_seconds=0)

    def test_completed_session_cannot_advance(self) -> None:
        session = self.manager.start(shots=1, countdown_seconds=0)
        for _ in range(5):
            self.manager.advance(session.id)
        with self.assertRaises(InvalidTransition):
            self.manager.advance(session.id)

    def test_session_can_capture_from_registry_selected_camera(self) -> None:
        selected_camera = AlternateCamera()
        session = self.manager.start(shots=1, countdown_seconds=0, camera=selected_camera)

        self.assertEqual(session.camera_id, "mock-selected")
        for _ in range(5):
            session = self.manager.advance(session.id)
        self.assertEqual(session.camera_id, "mock-selected")

    def test_failed_camera_retries_once_then_saves_recent_preview_as_low_quality(self) -> None:
        failing_camera = FailingCamera()
        preview_frame = next(MockCamera().iter_preview_frames())
        session = self.manager.start(
            shots=1,
            countdown_seconds=0,
            camera=failing_camera,
            preview_frame_provider=lambda: preview_frame,
        )

        for _ in range(5):
            session = self.manager.advance(session.id)

        self.assertEqual(failing_camera.capture_attempts, 2)
        self.assertEqual(session.low_quality_photo_ids, session.photo_ids)
        saved_photo = (
            self.storage_dir / "events" / "default" / session.id / (f"{session.photo_ids[0]}.jpg")
        )
        self.assertEqual(saved_photo.read_bytes(), preview_frame)
        metadata = json.loads(
            (self.storage_dir / "events" / "default" / session.id / "session.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(metadata["low_quality_photo_ids"], session.photo_ids)

    def test_failed_camera_without_recent_preview_raises_after_one_retry(self) -> None:
        failing_camera = FailingCamera()
        session = self.manager.start(shots=1, countdown_seconds=0, camera=failing_camera)
        self.manager.advance(session.id)
        self.manager.advance(session.id)

        with self.assertRaisesRegex(RuntimeError, "after one retry"):
            self.manager.advance(session.id)
        self.assertEqual(failing_camera.capture_attempts, 2)

    def test_failed_camera_switches_to_available_capture_fallback(self) -> None:
        failing_camera = FailingCamera()
        fallback_camera = FallbackCamera()
        session = self.manager.start(
            shots=1,
            countdown_seconds=0,
            camera=failing_camera,
            fallback_camera_provider=lambda failed: (
                None if fallback_camera.camera_id in failed else fallback_camera
            ),
        )

        for _ in range(5):
            session = self.manager.advance(session.id)

        self.assertEqual(failing_camera.capture_attempts, 2)
        self.assertEqual(session.camera_id, fallback_camera.camera_id)
        self.assertTrue(session.camera_fallback)
        self.assertEqual(session.low_quality_photo_ids, [])
        self.assertTrue(
            (
                self.storage_dir / "events" / "default" / session.id / f"{session.photo_ids[0]}.ppm"
            ).is_file()
        )

    def test_preferred_camera_is_retried_between_shots_after_fallback(self) -> None:
        primary_camera = RecoveringCamera()
        fallback_camera = CountingFallbackCamera()

        def camera_provider(failed_camera_ids):
            if primary_camera.camera_id not in failed_camera_ids:
                return primary_camera
            if fallback_camera.camera_id not in failed_camera_ids:
                return fallback_camera
            return None

        session = self.manager.start(
            shots=2,
            countdown_seconds=0,
            camera=primary_camera,
            fallback_camera_provider=camera_provider,
        )

        for _ in range(20):
            if session.state is SessionState.DONE:
                break
            session = self.manager.advance(session.id)

        self.assertEqual(session.state, SessionState.DONE)
        self.assertEqual(primary_camera.capture_attempts, 3)
        self.assertEqual(fallback_camera.capture_attempts, 1)
        self.assertEqual(session.camera_id, primary_camera.camera_id)
        self.assertFalse(session.camera_fallback)


if __name__ == "__main__":
    unittest.main()

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


if __name__ == "__main__":
    unittest.main()
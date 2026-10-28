import os
import subprocess
import unittest
from unittest.mock import patch

from photobox.camera import WebcamCamera, camera_from_environment


class WebcamCameraTests(unittest.TestCase):
    @patch.dict(os.environ, {"PHOTOBOX_CAMERA": "mock"})
    def test_environment_can_select_mock_camera(self):
        self.assertEqual(camera_from_environment().camera_id, "mock-0")

    @patch.dict(
        os.environ,
        {"PHOTOBOX_CAMERA": "webcam", "PHOTOBOX_CAMERA_DEVICE": "/dev/video7"},
    )
    def test_environment_can_select_webcam_device(self):
        self.assertEqual(camera_from_environment().camera_id, "v4l2:/dev/video7")

    @patch("photobox.camera.shutil.which", return_value="/usr/bin/ffmpeg")
    @patch("photobox.camera.subprocess.run")
    def test_capture_returns_jpeg_from_configured_device(self, run, _which):
        image = b"\xff\xd8test-jpeg\xff\xd9"
        run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout=image, stderr=b""
        )

        captured = WebcamCamera("/dev/video2").capture_still()

        self.assertEqual(captured.data, image)
        self.assertEqual(captured.extension, "jpg")
        self.assertEqual(captured.media_type, "image/jpeg")
        self.assertIn("/dev/video2", run.call_args.args[0])
        self.assertEqual(run.call_args.kwargs["timeout"], 15.0)

    @patch("photobox.camera.shutil.which", return_value=None)
    def test_missing_ffmpeg_has_actionable_error(self, _which):
        with self.assertRaisesRegex(RuntimeError, "install ffmpeg"):
            WebcamCamera().capture_still()

    @patch("photobox.camera.shutil.which", return_value="/usr/bin/ffmpeg")
    @patch("photobox.camera.subprocess.run")
    def test_failed_capture_includes_ffmpeg_error(self, run, _which):
        run.return_value = subprocess.CompletedProcess(
            args=[], returncode=1, stdout=b"", stderr=b"device busy"
        )

        with self.assertRaisesRegex(RuntimeError, "device busy"):
            WebcamCamera().capture_still()


if __name__ == "__main__":
    unittest.main()
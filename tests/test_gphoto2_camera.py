import os
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from photobox.camera import GPhoto2Camera, camera_from_environment


@patch("photobox.camera.shutil.which", return_value="/usr/bin/gphoto2")
def test_gphoto2_camera_detects_attached_device(which):
    with patch(
        "photobox.camera.subprocess.run",
        return_value=subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout=b"Model                         Port\n------------------------------------------\nCamera Model                  usb:001,002\n",
            stderr=b"",
        ),
    ) as run:
        camera = GPhoto2Camera()

        assert camera.available is True
        assert camera.camera_id == "gphoto2:auto"
        assert run.call_args.args[0] == ["/usr/bin/gphoto2", "--auto-detect"]


@patch("photobox.camera.shutil.which", return_value="/usr/bin/gphoto2")
def test_gphoto2_capture_downloads_and_validates_jpeg(which):
    image = b"\xff\xd8camera-jpeg\xff\xd9"

    def run(command, **kwargs):
        image_path = Path(command[command.index("--filename") + 1])
        image_path.write_bytes(image)
        return subprocess.CompletedProcess(args=command, returncode=0, stdout=b"", stderr=b"")

    with patch("photobox.camera.subprocess.run", side_effect=run) as run_mock:
        captured = GPhoto2Camera(port="usb:001,002").capture_still()

    assert captured.data == image
    assert captured.extension == "jpg"
    assert captured.media_type == "image/jpeg"
    assert run_mock.call_args.args[0][:4] == [
        "/usr/bin/gphoto2",
        "--port",
        "usb:001,002",
        "--capture-image-and-download",
    ]


@patch("photobox.camera.shutil.which", return_value="/usr/bin/gphoto2")
def test_gphoto2_capture_reports_command_failure(which):
    with (
        patch(
            "photobox.camera.subprocess.run",
            return_value=subprocess.CompletedProcess(
                args=[], returncode=1, stdout=b"", stderr=b"camera disconnected"
            ),
        ),
        pytest.raises(RuntimeError, match="camera disconnected"),
    ):
        GPhoto2Camera().capture_still()


@patch("photobox.camera.shutil.which", return_value="/usr/bin/gphoto2")
def test_gphoto2_capture_reports_timeout(which):
    with (
        patch(
            "photobox.camera.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="gphoto2", timeout=30),
        ),
        pytest.raises(RuntimeError, match="Timed out during gphoto2 capture"),
    ):
        GPhoto2Camera().capture_still()


@patch("photobox.camera.shutil.which", return_value="/usr/bin/gphoto2")
def test_gphoto2_rejects_non_jpeg_still(which):
    def run(command, **kwargs):
        image_path = Path(command[command.index("--filename") + 1])
        image_path.write_bytes(b"not-a-jpeg")
        return subprocess.CompletedProcess(args=command, returncode=0, stdout=b"", stderr=b"")

    with (
        patch("photobox.camera.subprocess.run", side_effect=run),
        pytest.raises(RuntimeError, match="invalid JPEG"),
    ):
        GPhoto2Camera().capture_still()


@patch("photobox.camera.shutil.which", return_value="/usr/bin/gphoto2")
def test_generic_gphoto2_does_not_claim_unverified_preview(which):
    camera = GPhoto2Camera()

    assert camera.capabilities().preview is False
    with pytest.raises(RuntimeError, match="not enabled"):
        camera.iter_preview_frames()


@patch("photobox.camera.shutil.which", return_value=None)
def test_gphoto2_is_unavailable_without_cli(which):
    assert GPhoto2Camera().available is False
    with pytest.raises(RuntimeError, match="install gphoto2"):
        GPhoto2Camera().capture_still()


@patch.dict(os.environ, {"PHOTOBOX_CAMERA": "gphoto2", "PHOTOBOX_GPHOTO2_PORT": "usb:001,002"})
def test_environment_selects_gphoto2_camera():
    camera = camera_from_environment()

    assert isinstance(camera, GPhoto2Camera)
    assert camera.camera_id == "gphoto2:usb:001,002"

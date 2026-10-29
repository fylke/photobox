import os
import shutil
import subprocess
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class CapturedImage:
    data: bytes
    extension: str
    media_type: str


class Camera(Protocol):
    @property
    def camera_id(self) -> str: ...

    def capture_still(self) -> CapturedImage: ...


class MockCamera:
    """Generate a small valid PPM image for development and tests."""

    camera_id = "mock-0"

    def capture_still(self) -> CapturedImage:
        width, height = 64, 48
        header = f"P6\n{width} {height}\n255\n".encode("ascii")
        pixels = bytes((40, 120, 200)) * (width * height)
        return CapturedImage(
            data=header + pixels,
            extension="ppm",
            media_type="image/x-portable-pixmap",
        )


class WebcamCamera:
    def __init__(self, device: str = "/dev/video0", timeout: float = 15.0):
        self.device = device
        self.timeout = timeout

    @property
    def camera_id(self) -> str:
        return f"v4l2:{self.device}"

    def capture_still(self) -> CapturedImage:
        ffmpeg = shutil.which("ffmpeg")
        if ffmpeg is None:
            raise RuntimeError("ffmpeg is required for webcam capture; install ffmpeg first")

        command = [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "video4linux2",
            "-i",
            self.device,
            "-frames:v",
            "1",
            "-f",
            "image2pipe",
            "-vcodec",
            "mjpeg",
            "pipe:1",
        ]
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                check=False,
                timeout=self.timeout,
            )
        except subprocess.TimeoutExpired as error:
            raise RuntimeError(f"Timed out capturing an image from {self.device}") from error
        except OSError as error:
            raise RuntimeError(f"Could not start ffmpeg for webcam {self.device}: {error}") from error

        if result.returncode != 0:
            detail = result.stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError(detail or f"Webcam capture failed for {self.device}")
        if not result.stdout.startswith(b"\xff\xd8"):
            raise RuntimeError(f"Webcam {self.device} returned an invalid JPEG image")

        return CapturedImage(
            data=result.stdout,
            extension="jpg",
            media_type="image/jpeg",
        )


def camera_from_environment() -> Camera:
    camera_type = os.environ.get("PHOTOBOX_CAMERA", "webcam").lower()
    if camera_type == "mock":
        return MockCamera()
    if camera_type == "webcam":
        device = os.environ.get("PHOTOBOX_CAMERA_DEVICE", "/dev/video0")
        return WebcamCamera(device)
    raise ValueError("PHOTOBOX_CAMERA must be 'webcam' or 'mock'")
import os
import shutil
import subprocess
import time
from collections.abc import Iterator
from dataclasses import dataclass
from io import BytesIO
from typing import Protocol

from PIL import Image


@dataclass(frozen=True)
class CapturedImage:
    data: bytes
    extension: str
    media_type: str


class Camera(Protocol):
    @property
    def camera_id(self) -> str: ...

    def capture_still(self) -> CapturedImage: ...

    def iter_preview_frames(self) -> Iterator[bytes]: ...


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

    def iter_preview_frames(self) -> Iterator[bytes]:
        image = Image.new("RGB", (640, 480), (40, 120, 200))
        image_buffer = BytesIO()
        image.save(image_buffer, format="JPEG", quality=75)
        frame = image_buffer.getvalue()
        while True:
            yield frame
            time.sleep(0.125)


class WebcamCamera:
    def __init__(
        self,
        device: str = "/dev/video0",
        timeout: float = 15.0,
        preview_fps: int = 8,
        preview_width: int = 640,
    ):
        self.device = device
        self.timeout = timeout
        if not 1 <= preview_fps <= 30:
            raise ValueError("preview_fps must be between 1 and 30")
        if not 160 <= preview_width <= 1920:
            raise ValueError("preview_width must be between 160 and 1920")
        self.preview_fps = preview_fps
        self.preview_width = preview_width

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

    def iter_preview_frames(self) -> Iterator[bytes]:
        ffmpeg = shutil.which("ffmpeg")
        if ffmpeg is None:
            raise RuntimeError("ffmpeg is required for webcam preview; install ffmpeg first")

        command = [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "video4linux2",
            "-framerate",
            str(self.preview_fps),
            "-i",
            self.device,
            "-vf",
            f"scale={self.preview_width}:-2",
            "-q:v",
            "6",
            "-f",
            "image2pipe",
            "-vcodec",
            "mjpeg",
            "pipe:1",
        ]
        process: subprocess.Popen[bytes] | None = None
        frame_count = 0
        try:
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                bufsize=0,
            )
            if process.stdout is None:
                raise RuntimeError("Could not read webcam preview stream")

            buffer = bytearray()
            read_chunk = getattr(process.stdout, "read1", process.stdout.read)
            while chunk := read_chunk(8192):
                buffer.extend(chunk)
                while True:
                    start = buffer.find(b"\xff\xd8")
                    if start < 0:
                        if len(buffer) > 1:
                            del buffer[:-1]
                        break
                    if start > 0:
                        del buffer[:start]
                    end = buffer.find(b"\xff\xd9", 2)
                    if end < 0:
                        if len(buffer) > 5_000_000:
                            raise RuntimeError("Webcam preview frame exceeded the size limit")
                        break
                    frame = bytes(buffer[: end + 2])
                    del buffer[: end + 2]
                    frame_count += 1
                    yield frame

            if process.poll() not in (0, None) and frame_count == 0:
                raise RuntimeError(f"Webcam preview failed for {self.device}")
        except OSError as error:
            raise RuntimeError(f"Could not start ffmpeg for webcam preview: {error}") from error
        finally:
            if process is not None:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
                if process.stdout is not None:
                    process.stdout.close()


def camera_from_environment() -> Camera:
    camera_type = os.environ.get("PHOTOBOX_CAMERA", "webcam").lower()
    if camera_type == "mock":
        return MockCamera()
    if camera_type == "webcam":
        device = os.environ.get("PHOTOBOX_CAMERA_DEVICE", "/dev/video0")
        return WebcamCamera(device)
    raise ValueError("PHOTOBOX_CAMERA must be 'webcam' or 'mock'")
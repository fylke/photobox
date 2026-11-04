import os
import shutil
import subprocess
import tempfile
import time
from collections.abc import Iterator
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Protocol

from PIL import Image


@dataclass(frozen=True)
class CapturedImage:
    data: bytes
    extension: str
    media_type: str
    low_quality: bool = False


@dataclass(frozen=True)
class CameraCapabilities:
    preview: bool
    still_capture: bool
    max_resolution: tuple[int, int] | None = None
    controls: tuple[str, ...] = ()
    live_view: bool = False


class Camera(Protocol):
    @property
    def camera_id(self) -> str: ...

    @property
    def available(self) -> bool: ...

    def capabilities(self) -> CameraCapabilities: ...

    def capture_still(self) -> CapturedImage: ...

    def iter_preview_frames(self) -> Iterator[bytes]: ...


class UnavailableCamera:
    camera_id = "none"

    @property
    def available(self) -> bool:
        return False

    def capabilities(self) -> CameraCapabilities:
        return CameraCapabilities(preview=False, still_capture=False)

    def capture_still(self) -> CapturedImage:
        raise RuntimeError("No camera is currently available.")

    def iter_preview_frames(self) -> Iterator[bytes]:
        raise RuntimeError("No camera preview is currently available.")


class MockCamera:
    """Generate a small valid PPM image for development and tests."""

    camera_id = "mock-0"

    @property
    def available(self) -> bool:
        return True

    def capabilities(self) -> CameraCapabilities:
        return CameraCapabilities(
            preview=True,
            still_capture=True,
            max_resolution=(640, 480),
            live_view=True,
        )

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

    @property
    def available(self) -> bool:
        return shutil.which("ffmpeg") is not None and os.path.exists(self.device)

    def capabilities(self) -> CameraCapabilities:
        return CameraCapabilities(
            preview=True,
            still_capture=True,
            live_view=True,
        )

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
            raise RuntimeError(
                f"Could not start ffmpeg for webcam {self.device}: {error}"
            ) from error

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


class GPhoto2Camera:
    def __init__(
        self,
        port: str | None = None,
        timeout: float = 30.0,
    ):
        self.port = port
        self.timeout = timeout

    @property
    def camera_id(self) -> str:
        return f"gphoto2:{self.port or 'auto'}"

    @property
    def available(self) -> bool:
        executable = shutil.which("gphoto2")
        if executable is None:
            return False
        command = [executable]
        if self.port:
            command.extend(["--port", self.port, "--summary"])
        else:
            command.append("--auto-detect")
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                check=False,
                timeout=min(self.timeout, 5),
            )
        except (OSError, subprocess.TimeoutExpired):
            return False
        if result.returncode != 0:
            return False
        output = result.stdout.decode("utf-8", errors="replace")
        return bool(self.port) or any(
            line.strip() and not set(line.strip()) <= {"-"} for line in output.splitlines()[2:]
        )

    def capabilities(self) -> CameraCapabilities:
        return CameraCapabilities(
            preview=False,
            still_capture=True,
            live_view=False,
        )

    def capture_still(self) -> CapturedImage:
        executable = shutil.which("gphoto2")
        if executable is None:
            raise RuntimeError("gphoto2 is required for DSLR capture; install gphoto2 first")

        with tempfile.TemporaryDirectory(prefix="photobox-gphoto2-") as directory:
            image_path = Path(directory) / "capture.jpg"
            command = self._command(
                executable, ["--capture-image-and-download", "--filename", str(image_path)]
            )
            result = self._run(command, "capture")
            if result.returncode != 0:
                detail = result.stderr.decode("utf-8", errors="replace").strip()
                raise RuntimeError(detail or "gphoto2 still capture failed")
            if not image_path.is_file():
                raise RuntimeError("gphoto2 completed without downloading a still image")
            image = image_path.read_bytes()
            if not image.startswith(b"\xff\xd8"):
                raise RuntimeError("gphoto2 returned an invalid JPEG image")

        return CapturedImage(data=image, extension="jpg", media_type="image/jpeg")

    def iter_preview_frames(self) -> Iterator[bytes]:
        raise RuntimeError("Live preview is not enabled for the generic gphoto2 profile.")

    def _command(self, executable: str, arguments: list[str]) -> list[str]:
        command = [executable]
        if self.port:
            command.extend(["--port", self.port])
        return [*command, *arguments]

    def _run(self, command: list[str], operation: str) -> subprocess.CompletedProcess[bytes]:
        try:
            return subprocess.run(
                command,
                capture_output=True,
                check=False,
                timeout=self.timeout,
            )
        except subprocess.TimeoutExpired as error:
            raise RuntimeError(f"Timed out during gphoto2 {operation}") from error
        except OSError as error:
            raise RuntimeError(f"Could not start gphoto2 for {operation}: {error}") from error


def camera_from_environment() -> Camera:
    camera_type = os.environ.get("PHOTOBOX_CAMERA", "webcam").lower()
    if camera_type == "mock":
        return MockCamera()
    if camera_type == "webcam":
        device = os.environ.get("PHOTOBOX_CAMERA_DEVICE", "/dev/video0")
        return WebcamCamera(device)
    if camera_type == "gphoto2":
        port = os.environ.get("PHOTOBOX_GPHOTO2_PORT")
        return GPhoto2Camera(port)
    raise ValueError("PHOTOBOX_CAMERA must be 'webcam', 'gphoto2', or 'mock'")

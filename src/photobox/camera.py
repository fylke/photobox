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
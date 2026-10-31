import pytest

from photobox.camera import CameraCapabilities, MockCamera
from photobox.camera_registry import CameraRegistry, camera_registry_from_environment


class IdentifiedCamera(MockCamera):
    def __init__(self, camera_id: str, available: bool = True):
        self._camera_id = camera_id
        self._available = available

    @property
    def camera_id(self) -> str:
        return self._camera_id

    @property
    def available(self) -> bool:
        return self._available


class CaptureOnlyCamera(IdentifiedCamera):
    def capabilities(self) -> CameraCapabilities:
        return CameraCapabilities(preview=False, still_capture=True)


def test_registry_assigns_default_roles_to_first_camera():
    first = IdentifiedCamera("webcam:front")
    second = IdentifiedCamera("webcam:side")
    registry = CameraRegistry([first, second])

    assert registry.camera_for_role("capture") is first
    assert registry.camera_for_role("preview") is first
    assert registry.descriptors()[1].roles == ()


def test_registry_selects_role_camera_within_client_binding():
    preview = IdentifiedCamera("webcam:preview")
    capture = IdentifiedCamera("dslr:capture")
    registry = CameraRegistry(
        [preview, capture],
        roles={
            preview.camera_id: {"preview"},
            capture.camera_id: {"capture"},
        },
        bindings={"phone-a": (capture.camera_id, preview.camera_id)},
    )

    assert registry.camera_for_role("preview", "phone-a") is preview
    assert registry.camera_for_role("capture", "phone-a") is capture
    assert registry.bound_camera_ids("unbound-phone") == (
        preview.camera_id,
        capture.camera_id,
    )


def test_registry_skips_unavailable_camera_for_role_selection():
    unavailable = IdentifiedCamera("webcam:unavailable", available=False)
    available = IdentifiedCamera("webcam:available")
    registry = CameraRegistry(
        [unavailable, available],
        roles={
            unavailable.camera_id: {"preview"},
            available.camera_id: {"preview"},
        },
    )

    assert registry.camera_for_role("preview") is available
    assert registry.camera_for_role("preview", available_only=False) is unavailable
    assert registry.descriptors()[0].available is False


def test_registry_can_select_an_alternate_role_camera_excluding_failed_ids():
    primary = IdentifiedCamera("dslr:capture")
    fallback = IdentifiedCamera("webcam:capture")
    registry = CameraRegistry(
        [primary, fallback],
        roles={
            primary.camera_id: {"capture"},
            fallback.camera_id: {"capture"},
        },
    )

    assert registry.camera_for_role("capture", exclude_camera_ids={primary.camera_id}) is fallback


def test_registry_skips_cameras_without_the_requested_capability():
    dslr = CaptureOnlyCamera("dslr:capture")
    webcam = IdentifiedCamera("webcam:preview")
    registry = CameraRegistry(
        [dslr, webcam],
        roles={
            dslr.camera_id: {"preview", "capture"},
            webcam.camera_id: {"preview"},
        },
    )

    assert registry.camera_for_role("preview") is webcam
    assert registry.camera_for_role("capture") is dslr


def test_registry_only_returns_a_recent_preview_frame(monkeypatch):
    clock = [100.0]
    monkeypatch.setattr("photobox.camera_registry.time.monotonic", lambda: clock[0])
    camera = IdentifiedCamera("webcam:preview")
    registry = CameraRegistry([camera])
    frame = b"\xff\xd8frame\xff\xd9"
    registry.record_preview_frame(camera.camera_id, frame)

    assert registry.latest_preview_frame("phone-a") == frame
    clock[0] += 11
    assert registry.latest_preview_frame("phone-a") is None


def test_registry_rejects_duplicate_ids_and_invalid_bindings():
    first = IdentifiedCamera("camera:one")
    duplicate = IdentifiedCamera("camera:one")
    with pytest.raises(ValueError, match="unique"):
        CameraRegistry([first, duplicate])

    with pytest.raises(ValueError, match="invalid camera"):
        CameraRegistry([first], bindings={"phone-a": ("camera:missing",)})


def test_registry_rejects_missing_or_unsupported_roles():
    first = IdentifiedCamera("camera:one")
    second = IdentifiedCamera("camera:two")

    with pytest.raises(ValueError, match="every registered camera"):
        CameraRegistry([first, second], roles={first.camera_id: {"capture"}})

    with pytest.raises(ValueError, match="only contain"):
        CameraRegistry([first], roles={first.camera_id: {"record"}})


def test_gphoto2_environment_adds_webcam_preview_and_capture_fallback(monkeypatch):
    monkeypatch.setenv("PHOTOBOX_CAMERA", "gphoto2")
    monkeypatch.setenv("PHOTOBOX_CAMERA_DEVICE", "/dev/video9")
    monkeypatch.setenv("PHOTOBOX_GPHOTO2_PORT", "usb:001,002")

    registry = camera_registry_from_environment()

    assert [descriptor.camera_id for descriptor in registry.descriptors()] == [
        "gphoto2:usb:001,002",
        "v4l2:/dev/video9",
    ]
    assert registry.descriptors()[0].roles == ("capture",)
    assert registry.descriptors()[1].roles == ("preview", "capture")


@pytest.mark.parametrize(
    ("dslr_available", "expected_capture_id"),
    [(True, "gphoto2:auto"), (False, "v4l2:/dev/video9")],
)
def test_gphoto2_registry_uses_webcam_capture_fallback(
    monkeypatch, dslr_available, expected_capture_id
):
    monkeypatch.setenv("PHOTOBOX_CAMERA", "gphoto2")
    monkeypatch.setenv("PHOTOBOX_CAMERA_DEVICE", "/dev/video9")
    monkeypatch.setattr(
        "photobox.camera.GPhoto2Camera.available",
        property(lambda self: dslr_available),
    )
    monkeypatch.setattr(
        "photobox.camera.WebcamCamera.available",
        property(lambda self: True),
    )

    registry = camera_registry_from_environment()

    assert registry.camera_for_role("capture").camera_id == expected_capture_id
    assert registry.camera_for_role("preview").camera_id == "v4l2:/dev/video9"

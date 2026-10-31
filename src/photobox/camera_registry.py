from __future__ import annotations

import os
import time
from collections import deque
from dataclasses import dataclass
from threading import Event, Lock, Thread
from typing import Literal

from photobox.camera import (
    Camera,
    CameraCapabilities,
    GPhoto2Camera,
    WebcamCamera,
    camera_from_environment,
)

CameraRole = Literal["preview", "capture"]
_PREVIEW_FRAME_MAX_AGE_SECONDS = 10
_GIF_PREVIEW_MAX_FRAMES = 8
_GIF_PREVIEW_SAMPLE_SECONDS = 0.25
_CAMERA_AVAILABILITY_POLL_SECONDS = 5


@dataclass(frozen=True)
class CameraDescriptor:
    camera_id: str
    available: bool
    roles: tuple[CameraRole, ...]
    capabilities: CameraCapabilities

    def as_dict(self) -> dict[str, object]:
        return {
            "camera_id": self.camera_id,
            "available": self.available,
            "roles": list(self.roles),
            "capabilities": {
                "preview": self.capabilities.preview,
                "still_capture": self.capabilities.still_capture,
                "max_resolution": self.capabilities.max_resolution,
                "controls": list(self.capabilities.controls),
                "live_view": self.capabilities.live_view,
            },
        }


class CameraRegistry:
    def __init__(
        self,
        cameras: list[Camera],
        roles: dict[str, set[CameraRole]] | None = None,
        bindings: dict[str, tuple[str, ...]] | None = None,
        *,
        initial_availability: dict[str, bool] | None = None,
    ):
        self._cameras: dict[str, Camera] = {}
        for camera in cameras:
            if not camera.camera_id or camera.camera_id in self._cameras:
                raise ValueError(f"Camera IDs must be non-empty and unique: {camera.camera_id!r}")
            self._cameras[camera.camera_id] = camera

        self._availability_lock = Lock()
        self._availability = initial_availability or {
            camera_id: camera.available for camera_id, camera in self._cameras.items()
        }
        self._monitor_lock = Lock()
        self._monitor_stop = Event()
        self._monitor_thread: Thread | None = None

        if roles is None:
            first_camera_id = next(iter(self._cameras), None)
            self._roles: dict[str, set[CameraRole]] = {
                camera_id: ({"preview", "capture"} if camera_id == first_camera_id else set())
                for camera_id in self._cameras
            }
        else:
            unknown_ids = roles.keys() - self._cameras.keys()
            missing_ids = self._cameras.keys() - roles.keys()
            if unknown_ids or missing_ids:
                raise ValueError("Camera roles must be specified for every registered camera.")
            if any(
                not assigned_roles <= {"preview", "capture"} for assigned_roles in roles.values()
            ):
                raise ValueError("Camera roles may only contain 'preview' or 'capture'.")
            self._roles = {
                camera_id: set(assigned_roles) for camera_id, assigned_roles in roles.items()
            }

        self._bindings = dict(bindings or {})
        self._configuration_lock = Lock()
        self._preview_frames: dict[str, deque[tuple[float, bytes]]] = {}
        self._latest_preview_frames: dict[str, tuple[float, bytes]] = {}
        self._preview_lock = Lock()
        for client_id, camera_ids in self._bindings.items():
            if not client_id or not camera_ids:
                raise ValueError("Camera bindings require a client ID and at least one camera.")
            if (
                len(set(camera_ids)) != len(camera_ids)
                or not set(camera_ids) <= self._cameras.keys()
            ):
                raise ValueError(f"Camera binding for {client_id!r} references an invalid camera.")

    def descriptors(self) -> list[CameraDescriptor]:
        with self._configuration_lock:
            roles = {camera_id: set(value) for camera_id, value in self._roles.items()}
        with self._availability_lock:
            availability = self._availability.copy()
        return [
            CameraDescriptor(
                camera_id=camera_id,
                available=availability[camera_id],
                roles=tuple(role for role in ("preview", "capture") if role in roles[camera_id]),
                capabilities=camera.capabilities(),
            )
            for camera_id, camera in self._cameras.items()
        ]

    def camera_for_role(
        self,
        role: CameraRole,
        client_id: str | None = None,
        *,
        available_only: bool = True,
        exclude_camera_ids: set[str] | None = None,
    ) -> Camera | None:
        with self._configuration_lock:
            bound_ids = self._bindings.get(client_id) if client_id is not None else None
            candidates = bound_ids if bound_ids is not None else tuple(self._cameras)
            excluded = exclude_camera_ids or set()
            return next(
                (
                    self._cameras[camera_id]
                    for camera_id in candidates
                    if camera_id not in excluded
                    if role in self._roles[camera_id]
                    and (
                        self._cameras[camera_id].capabilities().preview
                        if role == "preview"
                        else self._cameras[camera_id].capabilities().still_capture
                    )
                    and (not available_only or self._camera_available(camera_id))
                ),
                None,
            )

    def bound_camera_ids(self, client_id: str) -> tuple[str, ...]:
        with self._configuration_lock:
            return self._bindings.get(client_id, tuple(self._cameras))

    def configuration(self) -> dict[str, dict[str, list[str]]]:
        with self._configuration_lock:
            return {
                "roles": {camera_id: sorted(roles) for camera_id, roles in self._roles.items()},
                "bindings": {
                    client_id: list(camera_ids) for client_id, camera_ids in self._bindings.items()
                },
            }

    def configure(
        self,
        roles: dict[str, set[CameraRole]],
        bindings: dict[str, tuple[str, ...]],
    ) -> None:
        candidate = self.with_configuration(roles, bindings)
        with self._configuration_lock:
            self._roles = candidate._roles
            self._bindings = candidate._bindings

    def with_configuration(
        self,
        roles: dict[str, set[CameraRole]],
        bindings: dict[str, tuple[str, ...]],
    ) -> CameraRegistry:
        with self._availability_lock:
            availability = self._availability.copy()
        return CameraRegistry(
            list(self._cameras.values()),
            roles,
            bindings,
            initial_availability=availability,
        )

    def record_preview_frame(self, camera_id: str, frame: bytes) -> None:
        if camera_id not in self._cameras:
            raise KeyError(f"Unknown camera ID: {camera_id}")
        if len(frame) > 5_000_000:
            raise ValueError("Preview frame exceeds the 5 MB limit.")
        if not frame.startswith(b"\xff\xd8") or not frame.endswith(b"\xff\xd9"):
            return
        now = time.monotonic()
        with self._preview_lock:
            self._latest_preview_frames[camera_id] = (now, frame)
            samples = self._preview_frames.setdefault(
                camera_id,
                deque(maxlen=_GIF_PREVIEW_MAX_FRAMES),
            )
            if samples and now - samples[-1][0] < _GIF_PREVIEW_SAMPLE_SECONDS:
                return
            samples.append((now, frame))

    def refresh_availability(self) -> dict[str, bool]:
        current = {camera_id: camera.available for camera_id, camera in self._cameras.items()}
        with self._availability_lock:
            self._availability = current
        return current.copy()

    def start_monitor(self) -> None:
        with self._monitor_lock:
            if self._monitor_thread is not None and self._monitor_thread.is_alive():
                return
            self._monitor_stop.clear()
            self._monitor_thread = Thread(
                target=self._monitor_availability,
                name="photobox-camera-monitor",
                daemon=True,
            )
            self._monitor_thread.start()

    def stop_monitor(self) -> None:
        with self._monitor_lock:
            thread = self._monitor_thread
            if thread is None:
                return
            self._monitor_stop.set()
        thread.join(timeout=_CAMERA_AVAILABILITY_POLL_SECONDS + 1)
        with self._monitor_lock:
            if self._monitor_thread is thread and not thread.is_alive():
                self._monitor_thread = None

    def _camera_available(self, camera_id: str) -> bool:
        with self._availability_lock:
            return self._availability[camera_id]

    def _monitor_availability(self) -> None:
        while True:
            self.refresh_availability()
            if self._monitor_stop.wait(_CAMERA_AVAILABILITY_POLL_SECONDS):
                return

    def latest_preview_frame(self, client_id: str) -> bytes | None:
        camera = self.camera_for_role("preview", client_id)
        if camera is None:
            return None
        with self._preview_lock:
            latest = self._latest_preview_frames.get(camera.camera_id)
        if latest is None or time.monotonic() - latest[0] > _PREVIEW_FRAME_MAX_AGE_SECONDS:
            return None
        return latest[1]

    def recent_preview_frames(self, client_id: str) -> list[bytes]:
        camera = self.camera_for_role("preview", client_id)
        if camera is None:
            return []
        now = time.monotonic()
        with self._preview_lock:
            samples = self._preview_frames.get(camera.camera_id, ())
            return [
                frame
                for timestamp, frame in samples
                if now - timestamp <= _PREVIEW_FRAME_MAX_AGE_SECONDS
            ]


def camera_registry_from_environment() -> CameraRegistry:
    if os.environ.get("PHOTOBOX_CAMERA", "webcam").lower() != "gphoto2":
        camera = camera_from_environment()
        return CameraRegistry([camera], initial_availability={camera.camera_id: False})

    device = os.environ.get("PHOTOBOX_CAMERA_DEVICE", "/dev/video0")
    port = os.environ.get("PHOTOBOX_GPHOTO2_PORT")
    dslr = GPhoto2Camera(port)
    webcam = WebcamCamera(device)
    return CameraRegistry(
        [dslr, webcam],
        roles={
            dslr.camera_id: {"capture"},
            webcam.camera_id: {"preview", "capture"},
        },
        initial_availability={
            dslr.camera_id: False,
            webcam.camera_id: False,
        },
    )

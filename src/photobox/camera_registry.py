from __future__ import annotations

import os
import time
from dataclasses import dataclass
from threading import Lock
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
    ):
        self._cameras: dict[str, Camera] = {}
        for camera in cameras:
            if not camera.camera_id or camera.camera_id in self._cameras:
                raise ValueError(f"Camera IDs must be non-empty and unique: {camera.camera_id!r}")
            self._cameras[camera.camera_id] = camera

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
        self._preview_frames: dict[str, tuple[float, bytes]] = {}
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
        return [
            CameraDescriptor(
                camera_id=camera_id,
                available=camera.available,
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
                    and (not available_only or self._cameras[camera_id].available)
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
        return CameraRegistry(list(self._cameras.values()), roles, bindings)

    def record_preview_frame(self, camera_id: str, frame: bytes) -> None:
        if camera_id not in self._cameras:
            raise KeyError(f"Unknown camera ID: {camera_id}")
        if len(frame) > 5_000_000:
            raise ValueError("Preview frame exceeds the 5 MB limit.")
        with self._preview_lock:
            self._preview_frames[camera_id] = (time.monotonic(), frame)

    def latest_preview_frame(self, client_id: str) -> bytes | None:
        camera = self.camera_for_role("preview", client_id)
        if camera is None:
            return None
        with self._preview_lock:
            latest = self._preview_frames.get(camera.camera_id)
        if latest is None or time.monotonic() - latest[0] > _PREVIEW_FRAME_MAX_AGE_SECONDS:
            return None
        return latest[1]


def camera_registry_from_environment() -> CameraRegistry:
    if os.environ.get("PHOTOBOX_CAMERA", "webcam").lower() != "gphoto2":
        return CameraRegistry([camera_from_environment()])

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
    )

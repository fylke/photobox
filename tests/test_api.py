import base64
import json
import os
from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from photobox.api import create_app
from photobox.camera import CapturedImage, MockCamera, UnavailableCamera
from photobox.camera_registry import CameraRegistry
from photobox.network import NetworkError, NetworkStatus
from photobox.pairing import hash_setup_pin

SETUP_PIN = "4829017365"


class FinitePreviewCamera(MockCamera):
    def iter_preview_frames(self):
        yield b"\xff\xd8first-frame\xff\xd9"
        yield b"\xff\xd8second-frame\xff\xd9"


class FakeNetworkManager:
    def __init__(self):
        self.credentials = None

    def status(self):
        return NetworkStatus(True, "setup", "Connected to the Photobox setup network.", "10.42.0.1")

    def configure_venue(self, ssid, password):
        if password == "badpassword":
            raise NetworkError("NetworkManager could not connect.")
        self.credentials = (ssid, password)
        return NetworkStatus(True, "venue", "Connected to venue Wi-Fi.", "192.168.1.25")


def paired_client(tmp_path, camera=None, network_manager=None):
    client = TestClient(
        create_app(
            camera=camera,
            storage_dir=tmp_path,
            setup_pin_hash=hash_setup_pin(SETUP_PIN),
            network_manager=network_manager,
        )
    )
    response = client.post("/api/pairing/claim", json={"pin": SETUP_PIN})
    assert response.status_code == 200
    return client


def test_mock_session_api_captures_and_persists(tmp_path):
    client = paired_client(tmp_path)

    assert client.get("/api/health").json() == {"status": "ok", "camera": "mock-0"}
    response = client.post("/api/sessions", json={"shots": 1, "countdown_seconds": 0})
    assert response.status_code == 201
    session = response.json()

    for _ in range(5):
        response = client.post(f"/api/sessions/{session['id']}/advance")
        assert response.status_code == 200
        session = response.json()

    assert session["state"] == "done"
    assert len(session["photo_ids"]) == 1
    session_dir = tmp_path / "events" / "default" / session["id"]
    assert (session_dir / f"{session['photo_ids'][0]}.ppm").is_file()
    assert (session_dir / "session.json").is_file()


def test_starting_second_active_session_returns_conflict(tmp_path):
    client = paired_client(tmp_path)

    first = client.post("/api/sessions", json={"shots": 1})
    second = client.post("/api/sessions", json={"shots": 1})

    assert first.status_code == 201
    assert second.status_code == 409


def test_captured_photo_can_be_downloaded(tmp_path):
    client = paired_client(tmp_path)
    session = client.post("/api/sessions", json={"shots": 1}).json()

    for _ in range(3):
        response = client.post(f"/api/sessions/{session['id']}/advance")
        session = response.json()

    photo_id = session["photo_ids"][0]
    response = client.get(f"/api/sessions/{session['id']}/photos/{photo_id}")

    assert response.status_code == 200
    assert response.content.startswith(b"P6\n64 48\n255\n")
    assert "attachment" in response.headers["content-disposition"]


def test_completed_session_gallery_is_scoped_and_includes_composition(tmp_path):
    admin = paired_client(tmp_path)
    guest = TestClient(admin.app)
    invitation_url = admin.post("/api/pairing/invitations").json()["url"]
    invitation = invitation_url.split("#/invite/", maxsplit=1)[1]
    assert guest.post("/api/pairing/redeem", json={"invitation": invitation}).status_code == 200

    session = admin.post("/api/sessions", json={"shots": 2, "countdown_seconds": 0}).json()
    for _ in range(8):
        response = admin.post(f"/api/sessions/{session['id']}/advance")
        assert response.status_code == 200
        session = response.json()

    gallery = guest.get(f"/api/sessions/{session['id']}/gallery")

    assert gallery.status_code == 200
    result = gallery.json()
    assert len(result["photos"]) == 2
    assert result["strip_url"] == f"/api/sessions/{session['id']}/media/strip"
    assert result["url"].endswith(f"#/gallery/{session['id']}")
    assert result["qr_data_url"].startswith("data:image/png;base64,")
    assert guest.get(result["strip_url"]).content.startswith(b"\xff\xd8")
    assert guest.get(result["photos"][0]["url"]).status_code == 200
    assert (
        guest.get("/api/sessions/00000000-0000-0000-0000-000000000001/gallery").status_code == 404
    )


def test_guest_can_create_and_download_session_gif(tmp_path):
    client = paired_client(tmp_path)
    session_id = "00000000-0000-0000-0000-000000000123"
    storage = client.app.state.session_manager.storage
    colors = ([255, 0, 0], [0, 0, 255])
    photo_ids = [
        storage.save_photo(
            session_id,
            CapturedImage(
                b"P6\n64 48\n255\n" + bytes(color) * (64 * 48),
                "ppm",
                "image/x-portable-pixmap",
            ),
        )
        for color in colors
    ]
    storage.save_session(
        {"id": session_id, "state": "done", "photo_ids": photo_ids, "shots_taken": 2}
    )

    response = client.post(f"/api/sessions/{session_id}/media/gif")

    assert response.status_code == 202
    assert response.json() == {"status": "processing"}
    gallery = client.get(f"/api/sessions/{session_id}/gallery").json()
    assert gallery["gif_status"] == "ready"
    assert gallery["gif_url"] == f"/api/sessions/{session_id}/media/gif"
    gif = client.get(gallery["gif_url"])
    assert gif.status_code == 200
    assert gif.headers["content-type"] == "image/gif"
    assert gif.content.startswith(b"GIF")


def test_gif_creation_reports_media_errors_in_gallery(tmp_path, monkeypatch):
    client = paired_client(tmp_path)
    session_id = "00000000-0000-0000-0000-000000000124"
    storage = client.app.state.session_manager.storage
    photo_ids = [storage.save_photo(session_id, MockCamera().capture_still()) for _ in range(2)]
    storage.save_session(
        {"id": session_id, "state": "done", "photo_ids": photo_ids, "shots_taken": 2}
    )

    def fail_gif(_session_id, _photo_ids):
        raise ValueError("source image is corrupt")

    monkeypatch.setattr(storage, "compose_gif", fail_gif)
    response = client.post(f"/api/sessions/{session_id}/media/gif")

    assert response.status_code == 202
    gallery = client.get(f"/api/sessions/{session_id}/gallery").json()
    assert gallery["gif_status"] == "failed"
    assert gallery["gif_error"] == "source image is corrupt"


def test_strip_storage_failure_is_reported_without_completing_session(tmp_path, monkeypatch):
    client = paired_client(tmp_path)
    session = client.post("/api/sessions", json={"shots": 1, "countdown_seconds": 0}).json()
    for _ in range(4):
        response = client.post(f"/api/sessions/{session['id']}/advance")
        assert response.status_code == 200
        session = response.json()
    assert session["state"] == "composing"

    def fail_composition(_session_id, _photo_ids):
        raise OSError("disk unavailable")

    monkeypatch.setattr(
        client.app.state.session_manager.storage,
        "compose_strip",
        fail_composition,
    )
    response = client.post(f"/api/sessions/{session['id']}/advance")

    assert response.status_code == 503
    assert "Could not compose the photo strip" in response.json()["detail"]
    assert client.app.state.session_manager.current.state.value == "composing"


def test_observer_cannot_download_active_session_photos(tmp_path):
    admin = paired_client(tmp_path)
    guest = TestClient(admin.app)
    invitation_url = admin.post("/api/pairing/invitations").json()["url"]
    invitation = invitation_url.split("#/invite/", maxsplit=1)[1]
    guest.post("/api/pairing/redeem", json={"invitation": invitation})
    session = admin.post("/api/sessions", json={"shots": 1, "countdown_seconds": 0}).json()
    for _ in range(3):
        session = admin.post(f"/api/sessions/{session['id']}/advance").json()
    photo_id = session["photo_ids"][0]

    assert guest.get(f"/api/sessions/{session['id']}/photos/{photo_id}").status_code == 403
    assert (
        guest.get(f"/api/sessions/{session['id']}/photos/{photo_id}?download=false").status_code
        == 200
    )


def test_gallery_and_photo_routes_require_pairing(tmp_path):
    client = TestClient(create_app(storage_dir=tmp_path))

    assert (
        client.get("/api/sessions/00000000-0000-0000-0000-000000000001/gallery").status_code == 401
    )
    assert (
        client.get("/api/sessions/00000000-0000-0000-0000-000000000001/media/strip").status_code
        == 401
    )
    assert (
        client.post("/api/sessions/00000000-0000-0000-0000-000000000001/media/gif").status_code
        == 401
    )
    assert (
        client.get("/api/sessions/00000000-0000-0000-0000-000000000001/media/gif").status_code
        == 401
    )


def test_missing_photo_returns_not_found(tmp_path):
    client = paired_client(tmp_path)

    response = client.get(
        "/api/sessions/00000000-0000-0000-0000-000000000001/"
        "photos/00000000-0000-0000-0000-000000000002"
    )

    assert response.status_code == 404


def test_screen_ui_is_served_from_root(tmp_path):
    client = TestClient(create_app(storage_dir=tmp_path))

    response = client.get("/")

    assert response.status_code == 200
    assert "Start session" in response.text
    assert "Continue" in response.text
    assert "Claim administrator access" in response.text
    assert "Create guest invitation" in response.text
    assert "Connect to venue Wi-Fi" in response.text
    assert "/api/network/status" in response.text
    assert "Join this booth" in response.text
    assert "Paired guest phones" in response.text
    assert "Manage guest access" in response.text
    assert "Take control" in response.text
    assert "setInterval" in response.text
    assert "Live camera preview" in response.text
    assert "No camera connected" in response.text
    assert "Session gallery" in response.text
    assert "Copy gallery link" in response.text
    assert "decodeURIComponent(window.location.hash)" in response.text


def test_unpaired_api_fails_closed_until_admin_claim(tmp_path):
    client = TestClient(create_app(storage_dir=tmp_path, setup_pin_hash=hash_setup_pin(SETUP_PIN)))

    assert client.get("/api/pairing/status").json() == {
        "configured": True,
        "claimed": False,
    }
    assert client.post("/api/sessions", json={"shots": 1}).status_code == 401
    assert client.post("/api/pairing/claim", json={"pin": "0000000000"}).status_code == 401

    claim = client.post("/api/pairing/claim", json={"pin": SETUP_PIN})

    assert claim.status_code == 200
    assert claim.json() == {"role": "admin"}
    assert claim.headers["set-cookie"].startswith("photobox_credential=")
    assert "httponly" in claim.headers["set-cookie"].lower()
    assert client.get("/api/pairing/status").json() == {
        "configured": True,
        "claimed": True,
    }


def test_unprovisioned_booth_does_not_offer_a_valid_claim(tmp_path):
    client = TestClient(create_app(storage_dir=tmp_path))

    assert client.get("/api/pairing/status").json() == {
        "configured": False,
        "claimed": False,
    }
    assert client.post("/api/pairing/claim", json={"pin": SETUP_PIN}).status_code == 401


def test_network_status_is_public_and_does_not_expose_credentials(tmp_path):
    client = TestClient(create_app(storage_dir=tmp_path, network_manager=FakeNetworkManager()))

    response = client.get("/api/network/status")

    assert response.status_code == 200
    assert response.json() == {
        "available": True,
        "mode": "setup",
        "message": "Connected to the Photobox setup network.",
        "address": "10.42.0.1",
    }


def test_camera_status_reports_capabilities_roles_and_availability(tmp_path):
    client = TestClient(
        create_app(storage_dir=tmp_path, camera_registry=CameraRegistry([MockCamera()]))
    )

    response = client.get("/api/cameras")

    assert response.status_code == 200
    assert response.json() == [
        {
            "camera_id": "mock-0",
            "available": True,
            "roles": ["preview", "capture"],
            "capabilities": {
                "preview": True,
                "still_capture": True,
                "max_resolution": [640, 480],
                "controls": [],
                "live_view": True,
            },
        }
    ]


def test_no_camera_keeps_status_available_and_rejects_capture_and_preview(tmp_path):
    registry = CameraRegistry([UnavailableCamera()])
    client = TestClient(
        create_app(
            storage_dir=tmp_path,
            setup_pin_hash=hash_setup_pin(SETUP_PIN),
            camera_registry=registry,
        )
    )

    assert client.get("/api/health").json() == {"status": "ok", "camera": "none"}
    assert client.get("/api/cameras").json()[0]["available"] is False
    claim = client.post("/api/pairing/claim", json={"pin": SETUP_PIN})
    assert claim.status_code == 200
    assert client.post("/api/sessions", json={"shots": 1}).status_code == 503
    assert client.get("/api/preview").status_code == 503
    assert client.get("/api/pairing/status").json()["claimed"] is True


def test_only_admin_can_configure_venue_wifi(tmp_path):
    network = FakeNetworkManager()
    admin = paired_client(tmp_path, network_manager=network)

    unauthorized = TestClient(admin.app).post(
        "/api/network/venue",
        json={"ssid": "Venue", "password": "validpassword"},
    )
    configured = admin.post(
        "/api/network/venue",
        json={"ssid": "Venue", "password": "validpassword"},
    )

    assert unauthorized.status_code == 401
    assert configured.status_code == 200
    assert configured.json()["mode"] == "venue"
    assert "validpassword" not in configured.text
    assert network.credentials == ("Venue", "validpassword")


def test_failed_venue_wifi_configuration_is_reported(tmp_path):
    network = FakeNetworkManager()
    admin = paired_client(tmp_path, network_manager=network)

    response = admin.post(
        "/api/network/venue",
        json={"ssid": "Venue", "password": "badpassword"},
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "NetworkManager could not connect."


def test_invalid_venue_wifi_credentials_are_rejected_before_network_change(tmp_path):
    network = FakeNetworkManager()
    admin = paired_client(tmp_path, network_manager=network)

    response = admin.post(
        "/api/network/venue",
        json={"ssid": "Venue", "password": "short"},
    )

    assert response.status_code == 422
    assert network.credentials is None


@pytest.mark.skipif(os.name == "nt", reason="requires POSIX file permission bits")
def test_private_device_manifest_configures_first_admin_claim(tmp_path):
    device_config = tmp_path / "device.json"
    device_config.write_text(
        json.dumps(
            {
                "version": 1,
                "device_id": "A1B2C3D4",
                "setup_pin_hash": hash_setup_pin(SETUP_PIN),
                "wifi": {
                    "ssid": "Photobox-A1B2C3D4",
                    "password": "a-private-wifi-password",
                    "hidden": False,
                },
            }
        ),
        encoding="utf-8",
    )
    device_config.chmod(0o600)
    client = TestClient(create_app(storage_dir=tmp_path, device_config_path=device_config))

    assert client.get("/api/pairing/status").json() == {
        "configured": True,
        "claimed": False,
    }
    assert client.post("/api/pairing/claim", json={"pin": SETUP_PIN}).status_code == 200


@pytest.mark.skipif(os.name == "nt", reason="requires POSIX file permission bits")
def test_device_manifest_refuses_group_readable_secrets(tmp_path):
    device_config = tmp_path / "device.json"
    device_config.write_text(
        json.dumps(
            {
                "version": 1,
                "setup_pin_hash": hash_setup_pin(SETUP_PIN),
                "wifi": {
                    "ssid": "Photobox-A1B2C3D4",
                    "password": "a-private-wifi-password",
                    "hidden": False,
                },
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="mode 0600"):
        create_app(storage_dir=tmp_path, device_config_path=device_config)


def test_admin_can_invite_guest_and_guest_cannot_create_invitation(tmp_path):
    admin = paired_client(tmp_path)
    app = admin.app
    guest = TestClient(app)
    invitation_response = admin.post("/api/pairing/invitations")

    assert invitation_response.status_code == 201
    invitation_data = invitation_response.json()
    assert invitation_data["url"].startswith("http://testserver/#/invite/")
    assert "?" not in invitation_data["url"]
    qr_prefix, qr_payload = invitation_data["qr_data_url"].split(",", maxsplit=1)
    assert qr_prefix == "data:image/png;base64"
    qr_image = Image.open(BytesIO(base64.b64decode(qr_payload)))
    assert qr_image.format == "PNG"
    invitation = invitation_data["url"].split("#/invite/", maxsplit=1)[1]
    redeem = guest.post("/api/pairing/redeem", json={"invitation": invitation})

    assert redeem.status_code == 200
    assert redeem.json() == {"role": "guest"}
    assert "httponly" in redeem.headers["set-cookie"].lower()
    assert guest.post("/api/pairing/invitations").status_code == 403
    assert guest.post("/api/pairing/redeem", json={"invitation": invitation}).status_code == 401


def test_only_session_controller_can_advance(tmp_path):
    admin = paired_client(tmp_path)
    guest = TestClient(admin.app)
    invite_url = admin.post("/api/pairing/invitations").json()["url"]
    invitation = invite_url.split("#/invite/", maxsplit=1)[1]
    guest.post("/api/pairing/redeem", json={"invitation": invitation})
    session = admin.post("/api/sessions", json={"shots": 1}).json()

    response = guest.post(f"/api/sessions/{session['id']}/advance")

    assert response.status_code == 409
    assert response.json()["detail"] == "Session is controlled by another phone"


def test_session_response_marks_observers_read_only(tmp_path):
    admin = paired_client(tmp_path)
    guest = TestClient(admin.app)
    invitation_url = admin.post("/api/pairing/invitations").json()["url"]
    invitation = invitation_url.split("#/invite/", maxsplit=1)[1]
    guest.post("/api/pairing/redeem", json={"invitation": invitation})
    admin.post("/api/sessions", json={"shots": 1})

    admin_session = admin.get("/api/session").json()
    guest_session = guest.get("/api/session").json()

    assert admin_session["can_control"] is True
    assert guest_session["can_control"] is False
    assert guest_session["state"] == "armed"


def test_guest_can_take_control_after_controller_idle_timeout(monkeypatch, tmp_path):
    clock = [100.0]
    monkeypatch.setattr("photobox.api.time.monotonic", lambda: clock[0])
    admin = paired_client(tmp_path)
    guest = TestClient(admin.app)
    invitation_url = admin.post("/api/pairing/invitations").json()["url"]
    invitation = invitation_url.split("#/invite/", maxsplit=1)[1]
    guest.post("/api/pairing/redeem", json={"invitation": invitation})
    session = admin.post("/api/sessions", json={"shots": 1}).json()

    early = guest.post(f"/api/sessions/{session['id']}/advance")
    clock[0] += 61
    takeover = guest.post(f"/api/sessions/{session['id']}/advance")

    assert early.status_code == 409
    assert takeover.status_code == 200


def test_observer_can_explicitly_take_control_after_idle_timeout(monkeypatch, tmp_path):
    clock = [100.0]
    monkeypatch.setattr("photobox.api.time.monotonic", lambda: clock[0])
    admin = paired_client(tmp_path)
    guest = TestClient(admin.app)
    invitation_url = admin.post("/api/pairing/invitations").json()["url"]
    invitation = invitation_url.split("#/invite/", maxsplit=1)[1]
    guest.post("/api/pairing/redeem", json={"invitation": invitation})
    session = admin.post("/api/sessions", json={"shots": 1}).json()

    early = guest.post(f"/api/sessions/{session['id']}/control")
    clock[0] += 61
    takeover = guest.post(f"/api/sessions/{session['id']}/control")

    assert early.status_code == 409
    assert takeover.status_code == 200
    assert takeover.json()["can_control"] is True
    assert admin.post(f"/api/sessions/{session['id']}/advance").status_code == 409


def test_admin_can_list_and_revoke_guest_credentials(tmp_path):
    admin = paired_client(tmp_path)
    guest = TestClient(admin.app)
    invite_url = admin.post("/api/pairing/invitations").json()["url"]
    invitation = invite_url.split("#/invite/", maxsplit=1)[1]
    guest.post("/api/pairing/redeem", json={"invitation": invitation})
    credential_id = guest.get("/api/pairing/me").json()["credential_id"]

    guests = admin.get("/api/pairing/guests")

    assert guests.status_code == 200
    entries = guests.json()
    assert len(entries) == 1
    assert entries[0]["credential_id"] == credential_id
    assert isinstance(entries[0]["expires_at"], int)
    assert entries[0]["revoked"] is False
    assert guest.get("/api/pairing/guests").status_code == 403
    assert admin.delete(f"/api/pairing/credentials/{credential_id}").status_code == 204
    assert guest.get("/api/pairing/me").status_code == 401
    assert admin.get("/api/pairing/guests").json()[0]["revoked"] is True


def test_mutating_api_rejects_cross_origin_requests(tmp_path):
    admin = paired_client(tmp_path)

    response = admin.post(
        "/api/sessions",
        json={"shots": 1},
        headers={"Origin": "http://attacker.example"},
    )

    assert response.status_code == 403


def test_preview_stream_requires_pairing(tmp_path):
    client = TestClient(create_app(storage_dir=tmp_path))

    assert client.get("/api/preview").status_code == 401


def test_preview_stream_returns_multipart_jpeg_frames(tmp_path):
    client = paired_client(tmp_path, camera=FinitePreviewCamera())

    response = client.get("/api/preview")
    credential_id = client.get("/api/pairing/me").json()["credential_id"]

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("multipart/x-mixed-replace; boundary=frame")
    assert response.content.count(b"--frame\r\n") == 2
    assert b"first-frame" in response.content
    assert b"second-frame" in response.content
    assert (
        client.app.state.camera_registry.latest_preview_frame(credential_id)
        == b"\xff\xd8second-frame\xff\xd9"
    )

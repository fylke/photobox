from fastapi.testclient import TestClient

from photobox.api import create_app


def test_mock_session_api_captures_and_persists(tmp_path):
    client = TestClient(create_app(storage_dir=tmp_path))

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
    client = TestClient(create_app(storage_dir=tmp_path))

    first = client.post("/api/sessions", json={"shots": 1})
    second = client.post("/api/sessions", json={"shots": 1})

    assert first.status_code == 201
    assert second.status_code == 409


def test_captured_photo_can_be_downloaded(tmp_path):
    client = TestClient(create_app(storage_dir=tmp_path))
    session = client.post("/api/sessions", json={"shots": 1}).json()

    for _ in range(3):
        response = client.post(f"/api/sessions/{session['id']}/advance")
        session = response.json()

    photo_id = session["photo_ids"][0]
    response = client.get(f"/api/sessions/{session['id']}/photos/{photo_id}")

    assert response.status_code == 200
    assert response.content.startswith(b"P6\n64 48\n255\n")
    assert "attachment" in response.headers["content-disposition"]


def test_missing_photo_returns_not_found(tmp_path):
    client = TestClient(create_app(storage_dir=tmp_path))

    response = client.get(
        "/api/sessions/00000000-0000-0000-0000-000000000001/"
        "photos/00000000-0000-0000-0000-000000000002"
    )

    assert response.status_code == 404
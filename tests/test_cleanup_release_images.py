import json
import subprocess
from datetime import UTC, datetime
from unittest.mock import Mock

import pytest

from tools.cleanup_release_images import cleanup


@pytest.fixture(autouse=True)
def fixed_time(monkeypatch):
    clock = Mock(wraps=datetime)
    clock.now.return_value = datetime(2024, 4, 1, tzinfo=UTC)
    monkeypatch.setattr("tools.cleanup_release_images.datetime", clock)


def release(release_id, published_at, *, prerelease=True, draft=False):
    return {
        "id": release_id,
        "tag_name": f"v{release_id}",
        "published_at": published_at,
        "prerelease": prerelease,
        "draft": draft,
    }


def asset(asset_id, name):
    return {"id": asset_id, "name": name}


def test_cleanup_keeps_two_newest_across_stable_and_prereleases(monkeypatch):
    responses = {
        "repos/owner/repo/releases?per_page=100": [
            [
                release(1, "2024-01-01T00:00:00Z"),
                release(3, "2024-03-01T00:00:00Z", prerelease=False),
            ],
            [
                release(2, "2024-02-01T00:00:00Z"),
                release(4, None, draft=True),
                release(5, "2024-01-15T00:00:00Z"),
            ],
        ],
        "repos/owner/repo/releases/2/assets?per_page=100": [
            [asset(20, "new.img.xz"), asset(21, "SHA256SUMS")]
        ],
        "repos/owner/repo/releases/3/assets?per_page=100": [
            [asset(30, "stable.img.xz"), asset(31, "SHA256SUMS")]
        ],
        "repos/owner/repo/releases/1/assets?per_page=100": [
            [asset(10, "old.img.xz"), asset(11, "SHA256SUMS")],
            [asset(12, "country.img.xz"), asset(13, "notes.txt")],
        ],
        "repos/owner/repo/releases/5/assets?per_page=100": [
            [asset(50, "rollback.img.xz"), asset(51, "SHA256SUMS")]
        ],
    }
    deleted = []

    def run(command, **kwargs):
        if "--method" in command:
            deleted.append(command[-1])
            return subprocess.CompletedProcess(command, 0)
        return subprocess.CompletedProcess(command, 0, json.dumps(responses[command[-1]]))

    monkeypatch.setattr(subprocess, "run", run)
    cleanup("owner/repo")
    assert deleted == [
        "repos/owner/repo/releases/assets/50",
        "repos/owner/repo/releases/assets/51",
        "repos/owner/repo/releases/assets/10",
        "repos/owner/repo/releases/assets/11",
        "repos/owner/repo/releases/assets/12",
    ]


def test_cleanup_refuses_when_newest_has_no_image(monkeypatch):
    responses = {
        "repos/owner/repo/releases?per_page=100": [
            [
                release(2, "2024-02-01T00:00:00Z", prerelease=False),
                release(1, "2024-01-01T00:00:00Z"),
            ]
        ],
        "repos/owner/repo/releases/2/assets?per_page=100": [[asset(21, "SHA256SUMS")]],
        "repos/owner/repo/releases/1/assets?per_page=100": [[asset(10, "old.img.xz")]],
    }

    def run(command, **kwargs):
        assert "--method" not in command
        return subprocess.CompletedProcess(command, 0, json.dumps(responses[command[-1]]))

    monkeypatch.setattr(subprocess, "run", run)
    with pytest.raises(RuntimeError, match="has no .img.xz image"):
        cleanup("owner/repo")


def test_cleanup_does_not_delete_if_asset_listing_fails(monkeypatch):
    def run(command, **kwargs):
        assert "--method" not in command
        if "/assets?" in command[-1]:
            raise subprocess.CalledProcessError(1, command)
        return subprocess.CompletedProcess(
            command, 0, json.dumps([[release(1, "2024-01-01T00:00:00Z")]])
        )

    monkeypatch.setattr(subprocess, "run", run)
    with pytest.raises(subprocess.CalledProcessError):
        cleanup("owner/repo")


def test_cleanup_validates_all_asset_ids_before_deleting(monkeypatch):
    responses = {
        "repos/owner/repo/releases?per_page=100": [
            [
                release(2, "2024-02-01T00:00:00Z"),
                release(1, "2024-01-01T00:00:00Z"),
                release(3, "2024-01-15T00:00:00Z"),
            ]
        ],
        "repos/owner/repo/releases/2/assets?per_page=100": [[asset(20, "new.img.xz")]],
        "repos/owner/repo/releases/1/assets?per_page=100": [
            [asset(10, "old.img.xz"), asset("bad-id", "SHA256SUMS")]
        ],
        "repos/owner/repo/releases/3/assets?per_page=100": [[asset(30, "rollback.img.xz")]],
    }

    def run(command, **kwargs):
        assert "--method" not in command
        return subprocess.CompletedProcess(command, 0, json.dumps(responses[command[-1]]))

    monkeypatch.setattr(subprocess, "run", run)
    with pytest.raises(ValueError, match="Invalid asset ID"):
        cleanup("owner/repo")


@pytest.mark.parametrize(
    ("published_at", "should_delete"),
    [
        ("2024-03-25T00:00:01Z", False),
        ("2024-03-25T00:00:00Z", True),
        ("2024-03-24T23:59:59Z", True),
    ],
)
@pytest.mark.parametrize("prerelease", [True, False])
def test_cleanup_applies_seven_day_grace_period(
    monkeypatch, published_at, should_delete, prerelease
):
    responses = {
        "repos/owner/repo/releases?per_page=100": [[
            release(3, "2024-04-01T00:00:00Z"),
            release(2, "2024-03-31T00:00:00Z"),
            release(1, published_at, prerelease=prerelease),
        ]],
        "repos/owner/repo/releases/3/assets?per_page=100": [[asset(30, "new.img.xz")]],
        "repos/owner/repo/releases/2/assets?per_page=100": [[asset(20, "rollback.img.xz")]],
        "repos/owner/repo/releases/1/assets?per_page=100": [[asset(10, "old.img.xz")]],
    }
    deleted = []

    def run(command, **kwargs):
        if "--method" in command:
            deleted.append(command[-1])
            return subprocess.CompletedProcess(command, 0)
        return subprocess.CompletedProcess(command, 0, json.dumps(responses[command[-1]]))

    monkeypatch.setattr(subprocess, "run", run)
    cleanup("owner/repo")
    assert deleted == (["repos/owner/repo/releases/assets/10"] if should_delete else [])

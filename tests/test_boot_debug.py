from collections import namedtuple
from unittest.mock import Mock

import pytest

from photobox import boot_debug
from photobox.boot_debug import BootLog


def test_boot_log_rotates_with_bounded_total_size(tmp_path):
    log = BootLog(tmp_path, max_file_bytes=5, file_count=3, min_free_bytes=0)
    log.write(b"abcdefghijklmnopq")
    assert (tmp_path / "boot.log").read_bytes() == b"pq"
    assert (tmp_path / "boot.log.1").read_bytes() == b"klmno"
    assert (tmp_path / "boot.log.2").read_bytes() == b"fghij"
    assert sum(path.stat().st_size for path in tmp_path.iterdir()) <= 15


def test_boot_log_stops_before_filling_boot_partition(tmp_path, monkeypatch):
    disk_usage = namedtuple("disk_usage", ["total", "used", "free"])
    monkeypatch.setattr("photobox.boot_debug.shutil.disk_usage", lambda _: disk_usage(10, 4, 6))
    log = BootLog(tmp_path, max_file_bytes=5, file_count=3, min_free_bytes=5)
    with pytest.raises(OSError, match="Insufficient free space"):
        log.write(b"ab")
    assert not list(tmp_path.iterdir())


def test_default_log_limit_is_enforced_at_200_mib(tmp_path):
    log = BootLog(tmp_path)
    for name in ("boot.log", "boot.log.1", "boot.log.2", "boot.log.3"):
        with (tmp_path / name).open("wb") as file:
            file.truncate(50 * 1024 * 1024 - (1 if name == "boot.log" else 0))
    log.write(b"ab")
    assert (tmp_path / "boot.log").read_bytes() == b"b"
    assert sum(path.stat().st_size for path in tmp_path.iterdir()) <= 200 * 1024 * 1024


def test_exporter_stops_journalctl_if_log_write_fails(monkeypatch):
    process = Mock()
    process.stdout.read1.return_value = b"record"
    process.poll.return_value = None
    log = Mock()
    log.write.side_effect = OSError("disk full")
    monkeypatch.setattr(boot_debug, "BootLog", lambda _: log)
    monkeypatch.setattr(boot_debug.subprocess, "Popen", lambda *args, **kwargs: process)
    with pytest.raises(OSError, match="disk full"):
        boot_debug.main()
    process.terminate.assert_called_once()
    process.wait.assert_called_once()
    process.stdout.close.assert_called_once()

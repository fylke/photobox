import json
import os
import re
import stat

import pytest

from photobox import first_boot
from photobox.pairing import PairingManager, hash_setup_pin
from photobox.provision import provision_device


def test_apply_boot_config_installs_credentials_and_removes_boot_file(tmp_path, monkeypatch):
    manifest = {
        "version": 1,
        "device_id": "1234ABCD",
        "setup_pin_hash": hash_setup_pin("123456"),
        "wifi": {"ssid": "Photobox-1234ABCD", "password": "test_password123", "hidden": False, "country": "US"},
    }
    boot_config = tmp_path / "photobox-device.json"
    boot_config.write_text(json.dumps(manifest), encoding="utf-8")
    monkeypatch.setattr(first_boot.os, "fchown", lambda descriptor, owner, group: None)

    first_boot.apply_boot_config(boot_config, tmp_path, os.getuid(), os.getgid())

    config = tmp_path / "etc/photobox/device.json"
    environment = tmp_path / "etc/photobox/device.env"
    profile = tmp_path / "etc/NetworkManager/system-connections/photobox-setup.nmconnection"
    assert json.loads(config.read_text()) == manifest
    assert stat.S_IMODE(config.stat().st_mode) == 0o600
    assert "PHOTOBOX_WIFI_COUNTRY=US" in environment.read_text()
    assert "psk=test_password123" in profile.read_text()
    assert not boot_config.exists()


def test_invalid_boot_config_is_not_consumed(tmp_path):
    boot_config = tmp_path / "photobox-device.json"
    boot_config.write_text('{"version": 1}', encoding="utf-8")
    with pytest.raises((ValueError, TypeError)):
        first_boot.apply_boot_config(boot_config, tmp_path, os.getuid(), os.getgid())
    assert boot_config.exists()


def test_generated_bundle_can_be_imported_and_claimed(tmp_path, monkeypatch, capsys):
    bundle = tmp_path / "bundle"
    provision_device(["--wifi-country", "us", "--output-dir", str(bundle)])
    match = re.search(r"Setup PIN: ([0-9]{6})", capsys.readouterr().out)
    assert match is not None
    boot_config = tmp_path / "photobox-device.json"
    boot_config.write_bytes((bundle / "photobox-device.json").read_bytes())
    monkeypatch.setattr(first_boot.os, "fchown", lambda descriptor, owner, group: None)

    first_boot.apply_boot_config(boot_config, tmp_path, os.getuid(), os.getgid())

    installed = json.loads((tmp_path / "etc/photobox/device.json").read_text())
    pairing = PairingManager(tmp_path / "pairing.sqlite3", installed["setup_pin_hash"])
    assert pairing.authenticate(pairing.claim_admin(match.group(1)).token).role == "admin"


def test_first_boot_failure_can_be_retried(tmp_path, monkeypatch):
    bundle = tmp_path / "bundle"
    provision_device(["--wifi-country", "US", "--output-dir", str(bundle)])
    boot_config = tmp_path / "photobox-device.json"
    boot_config.write_bytes((bundle / "photobox-device.json").read_bytes())
    monkeypatch.setattr(first_boot.os, "fchown", lambda descriptor, owner, group: None)
    install_file = first_boot._install_file

    def fail_profile(path, data, owner, group):
        if path.name == "photobox-setup.nmconnection":
            raise OSError("simulated write failure")
        install_file(path, data, owner, group)

    monkeypatch.setattr(first_boot, "_install_file", fail_profile)
    with pytest.raises(OSError, match="simulated write failure"):
        first_boot.apply_boot_config(boot_config, tmp_path, os.getuid(), os.getgid())
    assert boot_config.exists()

    monkeypatch.setattr(first_boot, "_install_file", install_file)
    first_boot.apply_boot_config(boot_config, tmp_path, os.getuid(), os.getgid())
    assert not boot_config.exists()
    assert (tmp_path / "etc/NetworkManager/system-connections/photobox-setup.nmconnection").is_file()


def test_existing_device_configuration_is_not_replaced(tmp_path):
    bundle = tmp_path / "bundle"
    provision_device(["--wifi-country", "US", "--output-dir", str(bundle)])
    boot_config = tmp_path / "photobox-device.json"
    boot_config.write_bytes((bundle / "photobox-device.json").read_bytes())
    config = tmp_path / "etc/photobox/device.json"
    config.parent.mkdir(parents=True)
    config.write_text('{"existing": true}', encoding="utf-8")

    with pytest.raises(ValueError, match="different device configuration"):
        first_boot.apply_boot_config(boot_config, tmp_path, os.getuid(), os.getgid())

    assert boot_config.exists()
    assert json.loads(config.read_text()) == {"existing": True}
import json
import re
import sqlite3
import stat

import pytest

from photobox import provision
from photobox.pairing import PairingManager, hash_setup_pin
from photobox.provision import main, provision_device


def test_local_setup_command_prints_pin_once_and_stores_only_hash(
    monkeypatch,
    tmp_path,
    capsys,
):
    monkeypatch.setenv("PHOTOBOX_DATA_DIR", str(tmp_path))

    main()

    output = capsys.readouterr().out
    match = re.search(r"PIN: ([0-9]{10})", output)
    assert match is not None
    pin = match.group(1)

    with sqlite3.connect(tmp_path / "pairing.sqlite3") as connection:
        stored_values = " ".join(
            str(value)
            for row in connection.execute("SELECT value FROM settings")
            for value in row
        )
    assert pin not in stored_values

    pairing = PairingManager(tmp_path / "pairing.sqlite3", None)
    credential = pairing.claim_admin(pin)
    assert pairing.authenticate(credential.token).role == "admin"

    with pytest.raises(SystemExit):
        main()
    assert "already been initialized" in capsys.readouterr().err


def test_local_setup_command_refuses_to_replace_existing_pin(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("PHOTOBOX_DATA_DIR", str(tmp_path))
    PairingManager(tmp_path / "pairing.sqlite3", hash_setup_pin("1234567890"))

    with pytest.raises(SystemExit):
        main()

    assert "already been initialized" in capsys.readouterr().err


def test_device_bundle_contains_private_manifest_and_wifi_qr(monkeypatch, tmp_path, capsys):
    output_dir = tmp_path / "device-one"
    qr_payloads = []
    make_qr = provision.qrcode.make

    def record_qr_payload(payload):
        qr_payloads.append(payload)
        return make_qr(payload)

    monkeypatch.setattr(provision.qrcode, "make", record_qr_payload)

    provision_device(["--output-dir", str(output_dir)])

    output = capsys.readouterr().out
    pin_match = re.search(r"Setup PIN: ([0-9]{10})", output)
    assert pin_match is not None
    pin = pin_match.group(1)
    manifest_path = output_dir / "device.json"
    wifi_qr_path = output_dir / "wifi-join.png"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert manifest["version"] == 1
    assert manifest["setup_pin_hash"].startswith("scrypt$")
    assert pin not in manifest_path.read_text(encoding="utf-8")
    assert re.fullmatch(r"Photobox-[A-F0-9]{8}", manifest["wifi"]["ssid"])
    assert len(manifest["wifi"]["password"]) >= 20
    assert qr_payloads == [
        f"WIFI:T:WPA;S:{manifest['wifi']['ssid']};P:{manifest['wifi']['password']};H:false;;"
    ]
    assert wifi_qr_path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    assert "not a flashable OS image" in output
    assert stat.S_IMODE(output_dir.stat().st_mode) == 0o700
    assert stat.S_IMODE(manifest_path.stat().st_mode) == 0o600
    assert stat.S_IMODE(wifi_qr_path.stat().st_mode) == 0o600


def test_device_bundle_refuses_nonempty_output_directory(tmp_path, capsys):
    output_dir = tmp_path / "existing"
    output_dir.mkdir()
    existing_file = output_dir / "keep.txt"
    existing_file.write_text("existing setup", encoding="utf-8")

    with pytest.raises(SystemExit):
        provision_device(["--output-dir", str(output_dir)])

    assert existing_file.read_text(encoding="utf-8") == "existing setup"
    assert "not empty" in capsys.readouterr().err

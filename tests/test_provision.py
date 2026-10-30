import json
import lzma
import os
import re
import sqlite3
import stat
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from photobox import provision
from photobox.api import create_app
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
    assert "No bootable image was created" in output
    if os.name != "nt":
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


def test_device_bundle_provisions_compressed_base_image(monkeypatch, tmp_path, capsys):
    base_image = tmp_path / "generic.img.xz"
    base_image.write_bytes(lzma.compress(b"minimal base image"))
    output_dir = tmp_path / "device"
    commands = []
    installed_files = {}

    def fake_run_as_root(command):
        commands.append(command)
        if command[0] == "losetup" and "--find" in command:
            return "/dev/loop7"
        if command[0] == "lsblk":
            return "/dev/loop7 loop7\n/dev/loop7p1 bootfs\n/dev/loop7p2 rootfs"
        if command[0] == "install" and "-d" in command:
            Path(command[-1]).mkdir(parents=True, exist_ok=True)
        elif command[0] == "install":
            source = Path(command[-2])
            destination = Path(command[-1])
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(source.read_bytes())
            destination.chmod(0o600)
            installed_files[destination.name] = destination.read_bytes()
        return ""

    monkeypatch.setattr(provision.sys, "platform", "linux")
    monkeypatch.setattr(provision, "_run_as_root", fake_run_as_root)

    provision_device(
        [
            "--base-image",
            str(base_image),
            "--wifi-country",
            "gb",
            "--output-dir",
            str(output_dir),
        ]
    )

    output = capsys.readouterr().out
    pin = re.search(r"Setup PIN: ([0-9]{10})", output).group(1)
    image_path = output_dir / "photobox-device.img"
    manifest = json.loads(installed_files["device.json"])

    assert image_path.read_bytes() == b"minimal base image"
    if os.name != "nt":
        assert stat.S_IMODE(image_path.stat().st_mode) == 0o600
    assert pin not in installed_files["device.json"].decode("utf-8")
    assert manifest["setup_pin_hash"].startswith("scrypt$")
    assert manifest["wifi"]["country"] == "GB"
    assert installed_files["device.env"] == (
        b"PHOTOBOX_DEVICE_CONFIG=/etc/photobox/device.json\nPHOTOBOX_WIFI_COUNTRY=GB\n"
    )
    setup_profile = installed_files["photobox-setup.nmconnection"].decode("ascii")
    assert "id=Photobox setup" in setup_profile
    assert "mode=ap" in setup_profile
    assert f"ssid={manifest['wifi']['ssid']}" in setup_profile
    assert f"psk={manifest['wifi']['password']}" in setup_profile
    assert "method=shared" in setup_profile
    config_install = next(
        command
        for command in commands
        if command[0] == "install" and command[-1].endswith("/etc/photobox/device.json")
    )
    env_install = next(
        command
        for command in commands
        if command[0] == "install" and command[-1].endswith("/etc/photobox/device.env")
    )
    profile_install = next(
        command
        for command in commands
        if command[0] == "install"
        and command[-1].endswith("/NetworkManager/system-connections/photobox-setup.nmconnection")
    )
    assert config_install[config_install.index("-o") + 1] == "photobox"
    assert config_install[config_install.index("-g") + 1] == "photobox"
    assert env_install[env_install.index("-o") + 1] == "root"
    assert profile_install[profile_install.index("-m") + 1] == "0600"
    assert "Per-device image:" in output
    mount_dir = next(command[-1] for command in commands if command[0] == "mount")
    assert ["mount", "/dev/loop7p2", mount_dir] in commands
    assert ["umount", mount_dir] in commands
    assert ["losetup", "--detach", "/dev/loop7"] in commands
    assert any(
        command[0] == "ln"
        and command[-1].endswith("photobox-regulatory-domain.service")
        for command in commands
    )
    assert any(
        command[:2] == ["install", "-d"]
        and command[-1].endswith("multi-user.target.wants")
        for command in commands
    )


def test_image_provisioning_requires_wifi_country(tmp_path, capsys):
    base_image = tmp_path / "generic.img"
    base_image.write_bytes(b"generic image")

    with pytest.raises(SystemExit):
        provision_device(
            ["--base-image", str(base_image), "--output-dir", str(tmp_path / "device")]
        )

    assert "--wifi-country" in capsys.readouterr().err


@pytest.mark.parametrize("country", ["U1", "USA", "u", ""])
def test_image_provisioning_rejects_malformed_wifi_country(country, tmp_path, capsys):
    base_image = tmp_path / "generic.img"
    base_image.write_bytes(b"generic image")

    with pytest.raises(SystemExit):
        provision_device(
            [
                "--base-image",
                str(base_image),
                "--wifi-country",
                country,
                "--output-dir",
                str(tmp_path / "device"),
            ]
        )

    assert "--wifi-country" in capsys.readouterr().err


def test_device_bundle_removes_image_when_root_partition_is_missing(monkeypatch, tmp_path, capsys):
    base_image = tmp_path / "generic.img"
    base_image.write_bytes(b"generic image")
    output_dir = tmp_path / "device"
    commands = []

    def fake_run_as_root(command):
        commands.append(command)
        if command[0] == "losetup" and "--find" in command:
            return "/dev/loop8"
        if command[0] == "lsblk":
            return "/dev/loop8p1 bootfs"
        return ""

    monkeypatch.setattr(provision.sys, "platform", "linux")
    monkeypatch.setattr(provision, "_run_as_root", fake_run_as_root)

    with pytest.raises(SystemExit):
        provision_device(
            [
                "--base-image",
                str(base_image),
                "--wifi-country",
                "GB",
                "--output-dir",
                str(output_dir),
            ]
        )

    assert not (output_dir / "photobox-device.img").exists()
    assert ["losetup", "--detach", "/dev/loop8"] in commands
    assert "exactly one partition labeled rootfs" in capsys.readouterr().err


@pytest.mark.skipif(os.name == "nt", reason="requires POSIX file permission bits")
def test_generated_device_bundle_can_claim_admin_on_installed_host(tmp_path, capsys):
    bundle_dir = tmp_path / "device"
    provision_device(["--output-dir", str(bundle_dir)])
    output = capsys.readouterr().out
    pin = re.search(r"Setup PIN: ([0-9]{10})", output).group(1)
    client = TestClient(
        create_app(
            storage_dir=tmp_path / "runtime",
            device_config_path=bundle_dir / "device.json",
        )
    )

    claim = client.post("/api/pairing/claim", json={"pin": pin})

    assert claim.status_code == 200
    assert claim.json() == {"role": "admin"}

import hashlib
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest
import qrcode

from photobox import provision


def test_standalone_automatically_checks_release_files(tmp_path, monkeypatch, capsys):
    executable = tmp_path / "photobox-setup.exe"
    executable.write_bytes(b"executable")
    image = tmp_path / "photobox.img.xz"
    image.write_bytes(b"image")
    checksums = tmp_path / "SHA256SUMS"
    checksums.write_text(
        f"{hashlib.sha256(image.read_bytes()).hexdigest()}  {image.name}\n"
        f"{hashlib.sha256(executable.read_bytes()).hexdigest()}  {executable.name}\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(executable))
    output_dir = tmp_path / "device"

    provision.provision_device(["--wifi-country", "US", "--output-dir", str(output_dir)])

    output = capsys.readouterr()
    assert "SHA-256" not in output.out
    assert (output_dir / "photobox-device.json").exists()

    image.write_bytes(b"corrupt image")
    bad_output = tmp_path / "bad-device"
    with pytest.raises(SystemExit):
        provision.provision_device(["--wifi-country", "US", "--output-dir", str(bad_output)])
    assert "SHA-256 mismatch" in capsys.readouterr().err
    assert not bad_output.exists()


def test_standalone_rejects_missing_or_mismatched_release_files(tmp_path, monkeypatch, capsys):
    executable = tmp_path / "photobox-setup.exe"
    executable.write_bytes(b"executable")
    image = tmp_path / "photobox.img.xz"
    image.write_bytes(b"image")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(executable))
    output_dir = tmp_path / "device"
    args = ["--wifi-country", "US", "--output-dir", str(output_dir)]

    with pytest.raises(SystemExit):
        provision.provision_device(args)
    assert "Download verification failed" in capsys.readouterr().err
    assert not output_dir.exists()

    (tmp_path / "SHA256SUMS").write_text(
        f"{hashlib.sha256(image.read_bytes()).hexdigest()}  {image.name}\n"
        f"{'0' * 64}  {executable.name}\n",
        encoding="utf-8",
    )
    with pytest.raises(SystemExit):
        provision.provision_device(args)
    assert f"SHA-256 mismatch for {executable.name}" in capsys.readouterr().err
    assert not output_dir.exists()


def test_image_checksum_failure_creates_no_credentials(tmp_path, capsys):
    image = tmp_path / "photobox.img.xz"
    image.write_bytes(b"corrupt image")
    checksums = tmp_path / "SHA256SUMS"
    checksums.write_text(f"{'0' * 64}  {image.name}\n", encoding="utf-8")
    output_dir = tmp_path / "device"

    with pytest.raises(SystemExit):
        provision.provision_device(
            ["--verify-image", str(image), "--checksums", str(checksums),
             "--wifi-country", "US", "--output-dir", str(output_dir)]
        )

    assert "SHA-256 mismatch" in capsys.readouterr().err
    assert not output_dir.exists()


def test_image_checksum_success_creates_credentials(tmp_path, capsys):
    image = tmp_path / "photobox.img.xz"
    image.write_bytes(b"image content")
    checksums = tmp_path / "SHA256SUMS"
    checksums.write_text(
        f"{hashlib.sha256(image.read_bytes()).hexdigest()}  {image.name}\n", encoding="utf-8"
    )
    output_dir = tmp_path / "device"

    provision.provision_device(
        ["--verify-image", str(image), "--checksums", str(checksums),
         "--wifi-country", "US", "--output-dir", str(output_dir)]
    )

    assert "SHA-256 verified" in capsys.readouterr().out
    assert (output_dir / "photobox-device.json").exists()


@pytest.mark.parametrize("contents", ["", "not a checksum\n", f"{'0' * 64}  other.img.xz\n"])
def test_invalid_checksum_manifest_creates_no_credentials(tmp_path, capsys, contents):
    image = tmp_path / "photobox.img.xz"
    image.write_bytes(b"image content")
    checksums = tmp_path / "SHA256SUMS"
    checksums.write_text(contents, encoding="utf-8")
    output_dir = tmp_path / "device"

    with pytest.raises(SystemExit):
        provision.provision_device(
            ["--verify-image", str(image), "--checksums", str(checksums),
             "--wifi-country", "US", "--output-dir", str(output_dir)]
        )

    assert "Checksum verification failed" in capsys.readouterr().err
    assert not output_dir.exists()


def test_standalone_provisioner_runs_without_installed_python_packages(tmp_path):
    project_root = Path(__file__).parents[1]
    qrcode_package = Path(qrcode.__file__).parent
    bundle_path = tmp_path / "photobox-provision.pyz"
    output_dir = tmp_path / "device"
    subprocess.run(
        [
            sys.executable,
            str(project_root / "tools" / "build_provisioner.py"),
            "--qrcode-package",
            str(qrcode_package),
            "--output",
            str(bundle_path),
        ],
        check=True,
    )
    with zipfile.ZipFile(bundle_path) as bundle:
        assert "licenses/qrcode-LICENSE" in bundle.namelist()

    image = tmp_path / "photobox.img.xz"
    image.write_bytes(b"generic image")
    checksums = tmp_path / "SHA256SUMS"
    checksums.write_text(
        f"{hashlib.sha256(image.read_bytes()).hexdigest()}  {image.name}\n"
        f"{hashlib.sha256(bundle_path.read_bytes()).hexdigest()}  {bundle_path.name}\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        [
            sys.executable, "-S", str(bundle_path), "--verify-image", str(image),
            "--checksums", str(checksums), "--wifi-country", "us", "--output-dir", str(output_dir),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    assert "No bootable image was created" in result.stdout
    assert f"SHA-256 verified: {image.name}" in result.stdout
    assert f"SHA-256 verified: {bundle_path.name}" in result.stdout
    assert (output_dir / "photobox-device.json").is_file()
    assert (output_dir / "wifi-join.svg").is_file()

    bad_output = tmp_path / "bad-device"
    checksums.write_text(
        f"{hashlib.sha256(image.read_bytes()).hexdigest()}  {image.name}\n"
        f"{'0' * 64}  {bundle_path.name}\n",
        encoding="utf-8",
    )
    failed = subprocess.run(
        [
            sys.executable, "-S", str(bundle_path), "--verify-image", str(image),
            "--checksums", str(checksums), "--wifi-country", "us", "--output-dir", str(bad_output),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert failed.returncode != 0
    assert f"SHA-256 mismatch for {bundle_path.name}" in failed.stderr
    assert not bad_output.exists()


def test_image_provisioning_checks_privileges_before_creating_output(
    monkeypatch, tmp_path, capsys
):
    base_image = tmp_path / "generic.img"
    base_image.write_bytes(b"generic image")
    output_dir = tmp_path / "device"
    commands = []

    def reject_privilege_check(command):
        commands.append(command)
        raise RuntimeError("sudo: incorrect password")

    monkeypatch.setattr(provision, "_run_as_root", reject_privilege_check)

    with pytest.raises(SystemExit):
        provision.provision_device(
            [
                "--base-image",
                str(base_image),
                "--wifi-country",
                "GB",
                "--output-dir",
                str(output_dir),
            ]
        )

    assert commands == [["true"]]
    assert base_image.read_bytes() == b"generic image"
    assert not output_dir.exists()
    assert "incorrect password" in capsys.readouterr().err
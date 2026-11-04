import argparse
import json
import lzma
import os
import re
import secrets
import stat
import subprocess
import sys
import tempfile
import uuid
from io import BytesIO
from pathlib import Path
from shutil import copyfile, copyfileobj

import qrcode

from photobox.pairing import PairingError, PairingManager, generate_setup_pin, hash_setup_pin


def load_device_config(path: Path) -> dict[str, object]:
    path = Path(path)
    if path.is_symlink():
        raise ValueError("Device config must not be a symlink")
    try:
        mode = stat.S_IMODE(path.stat().st_mode)
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"Could not read device config: {error}") from error
    if mode & 0o077:
        raise ValueError("Device config must be readable only by its owner (mode 0600)")
    if not isinstance(manifest, dict) or manifest.get("version") != 1:
        raise ValueError("Unsupported device config version")

    pin_hash = manifest.get("setup_pin_hash")
    if not isinstance(pin_hash, str):
        raise TypeError("Device config is missing a setup PIN hash")
    try:
        algorithm, salt_hex, digest_hex = pin_hash.split("$", maxsplit=2)
        if algorithm != "scrypt" or len(bytes.fromhex(salt_hex)) != 16 or len(bytes.fromhex(digest_hex)) != 32:
            raise ValueError
    except ValueError as error:
        raise ValueError("Device config contains an invalid setup PIN hash") from error

    wifi = manifest.get("wifi")
    if (
        not isinstance(wifi, dict)
        or not isinstance(wifi.get("ssid"), str)
        or not isinstance(wifi.get("password"), str)
        or wifi.get("hidden") is not False
    ):
        raise ValueError("Device config contains invalid Wi-Fi settings")
    country = wifi.get("country")
    if country is not None and (
        not isinstance(country, str) or not re.fullmatch(r"[A-Z]{2}", country)
    ):
        raise ValueError("Device config contains an invalid Wi-Fi country code")
    return manifest


def main() -> None:
    data_dir = Path(os.environ.get("PHOTOBOX_DATA_DIR", "~/photobox")).expanduser()
    pairing = PairingManager(data_dir / "pairing.sqlite3", None)
    if pairing.status()["configured"]:
        print("Photobox setup has already been initialized; refusing to replace the PIN.", file=sys.stderr)
        raise SystemExit(1)

    pin = generate_setup_pin()
    try:
        pairing.provision_setup_pin(hash_setup_pin(pin))
    except PairingError as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1) from error

    print("One-time Photobox setup PIN (record it now; it will not be shown again):")
    print(f"PIN: {pin}")
    print("This command stores only a hash. The PIN is consumed when the first admin claims the booth.")


def provision_device(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Create private, per-device Photobox credentials and optionally provision an image."
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        type=Path,
        help="new or empty directory for private per-device provisioning files",
    )
    parser.add_argument(
        "--base-image",
        type=Path,
        help=(
            "optional Raspberry Pi OS Lite .img or .img.xz file to copy and provision (Linux only)"
        ),
    )
    parser.add_argument(
        "--wifi-country",
        help="two-letter ISO country code for the Pi Wi-Fi regulatory domain (required with --base-image)",
    )
    args = parser.parse_args(argv)
    if args.base_image is not None and (
        args.wifi_country is None or not re.fullmatch(r"[A-Za-z]{2}", args.wifi_country)
    ):
        parser.error("--base-image requires --wifi-country with a two-letter ISO country code.")
    wifi_country = args.wifi_country.upper() if args.wifi_country else None
    output_dir = args.output_dir.expanduser()
    if output_dir.is_symlink():
        print("Refusing to write provisioning secrets through a symlink.", file=sys.stderr)
        raise SystemExit(1)
    if output_dir.exists() and any(output_dir.iterdir()):
        print("Provisioning output directory is not empty; refusing to overwrite files.", file=sys.stderr)
        raise SystemExit(1)

    device_id = secrets.token_hex(4).upper()
    setup_pin = generate_setup_pin()
    wifi_ssid = f"Photobox-{device_id}"
    wifi_password = secrets.token_urlsafe(24)
    manifest = {
        "version": 1,
        "device_id": device_id,
        "setup_pin_hash": hash_setup_pin(setup_pin),
        "wifi": {
            "ssid": wifi_ssid,
            "password": wifi_password,
            "hidden": False,
            **({"country": wifi_country} if wifi_country else {}),
        },
    }
    qr_image = qrcode.make(
        f"WIFI:T:WPA;S:{_escape_wifi_qr_value(wifi_ssid)};P:{_escape_wifi_qr_value(wifi_password)};H:false;;"
    )
    qr_buffer = BytesIO()
    qr_image.save(qr_buffer, format="PNG")

    output_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(output_dir, 0o700)
    _write_private_file(
        output_dir / "device.json",
        (json.dumps(manifest, indent=2) + "\n").encode("utf-8"),
    )
    _write_private_file(output_dir / "wifi-join.png", qr_buffer.getvalue())
    if args.base_image is not None:
        try:
            image = _create_device_image(args.base_image.expanduser(), output_dir, manifest)
        except (
            OSError,
            RuntimeError,
            ValueError,
            TypeError,
            EOFError,
            lzma.LZMAError,
        ) as error:
            print(f"Could not provision image: {error}", file=sys.stderr)
            raise SystemExit(1) from error

    print("Per-device setup credentials created. Record these privately:")
    print(f"Device: {device_id}")
    print(f"Wi-Fi name: {wifi_ssid}")
    print(f"Wi-Fi password: {wifi_password}")
    print(f"Setup PIN: {setup_pin}")
    print(f"Private config and Wi-Fi QR: {output_dir}")
    if args.base_image is None:
        print("No bootable image was created; provide --base-image to provision one.")
    else:
        print(f"Per-device image: {image}")
        print("The image contains the setup PIN hash and Wi-Fi settings, not the setup PIN.")


def _create_device_image(
    base_image: Path, output_dir: Path, manifest: dict[str, object]
) -> Path:
    if sys.platform != "linux":
        raise RuntimeError("Image provisioning currently requires Linux.")
    if base_image.is_symlink() or not base_image.is_file():
        raise ValueError("Base image must be an existing regular file, not a symlink.")

    image_path = output_dir / "photobox-device.img"
    if image_path.exists():
        raise FileExistsError(f"Refusing to overwrite {image_path}")

    loop_device: str | None = None
    mounted = False
    succeeded = False
    try:
        if base_image.suffix == ".xz":
            with lzma.open(base_image, "rb") as source, image_path.open("wb") as target:
                copyfileobj(source, target)
        else:
            copyfile(base_image, image_path)
        os.chmod(image_path, 0o600)

        loop_device = _run_as_root(["losetup", "--find", "--show", "--partscan", str(image_path)])
        if not loop_device.startswith("/dev/"):
            raise RuntimeError("losetup did not return a valid loop device")
        _run_as_root(["udevadm", "settle"])
        partitions = _run_as_root(
            ["lsblk", "--raw", "--noheadings", "--output", "PATH,LABEL", loop_device]
        )
        root_partitions = []
        for line in partitions.splitlines():
            fields = line.split(maxsplit=1)
            if len(fields) == 2 and fields[1] == "rootfs":
                root_partitions.append(fields[0])
        if len(root_partitions) != 1:
            raise RuntimeError("Base image must contain exactly one partition labeled rootfs.")

        with tempfile.TemporaryDirectory(prefix="photobox-image-") as mount_dir:
            _run_as_root(["mount", root_partitions[0], mount_dir])
            mounted = True
            config_path = output_dir / "device.json"
            env_path = Path(mount_dir) / "photobox-device.env"
            wifi = manifest["wifi"]
            if not isinstance(wifi, dict) or not isinstance(wifi.get("country"), str):
                raise TypeError("A Wi-Fi country code is required to build the device image.")
            env_path.write_text(
                "PHOTOBOX_DEVICE_CONFIG=/etc/photobox/device.json\n"
                f"PHOTOBOX_WIFI_COUNTRY={wifi['country']}\n",
                encoding="ascii",
                newline="\n",
            )
            device_id = manifest["device_id"]
            if not isinstance(device_id, str):
                raise TypeError("Device config is missing a device ID.")
            setup_profile = (
                "[connection]\n"
                "id=Photobox setup\n"
                f"uuid={uuid.uuid5(uuid.NAMESPACE_DNS, 'photobox-' + device_id)}\n"
                "type=wifi\n"
                "autoconnect=true\n"
                "autoconnect-priority=10\n"
                "interface-name=wlan0\n"
                "\n[wifi]\n"
                "mode=ap\n"
                f"ssid={wifi['ssid']}\n"
                "band=bg\n"
                "\n[wifi-security]\n"
                "key-mgmt=wpa-psk\n"
                f"psk={wifi['password']}\n"
                "\n[ipv4]\n"
                "method=shared\n"
                "\n[ipv6]\n"
                "method=disabled\n"
            ).encode("ascii")
            _run_as_root(
                [
                    "install",
                    "-D",
                    "-o",
                    "photobox",
                    "-g",
                    "photobox",
                    "-m",
                    "0600",
                    str(config_path),
                    f"{mount_dir}/etc/photobox/device.json",
                ]
            )
            with tempfile.TemporaryDirectory(
                prefix="photobox-profile-", dir=output_dir
            ) as temp_dir:
                profile_source = Path(temp_dir) / "photobox-setup.nmconnection"
                profile_source.write_bytes(setup_profile)
                _run_as_root(
                    [
                        "install",
                        "-D",
                        "-o",
                        "root",
                        "-g",
                        "root",
                        "-m",
                        "0600",
                        str(profile_source),
                        f"{mount_dir}/etc/NetworkManager/system-connections/photobox-setup.nmconnection",
                    ]
                )
            _run_as_root(
                [
                    "install",
                    "-D",
                    "-o",
                    "root",
                    "-g",
                    "root",
                    "-m",
                    "0600",
                    str(env_path),
                    f"{mount_dir}/etc/photobox/device.env",
                ]
            )
            _run_as_root(
                [
                    "install",
                    "-d",
                    f"{mount_dir}/etc/systemd/system/multi-user.target.wants",
                ]
            )
            _run_as_root(
                [
                    "ln",
                    "-s",
                    "/etc/systemd/system/photobox-regulatory-domain.service",
                    f"{mount_dir}/etc/systemd/system/multi-user.target.wants/photobox-regulatory-domain.service",
                ]
            )
            _run_as_root(["umount", mount_dir])
            mounted = False
        succeeded = True
    finally:
        try:
            if mounted:
                _run_as_root(["umount", mount_dir])
        finally:
            try:
                if loop_device is not None:
                    _run_as_root(["losetup", "--detach", loop_device])
            finally:
                if not succeeded:
                    image_path.unlink(missing_ok=True)

    return image_path


def _run_as_root(command: list[str]) -> str:
    privileged_command = command
    if os.geteuid() != 0:
        privileged_command = ["sudo", *command]
    try:
        result = subprocess.run(
            privileged_command,
            check=True,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as error:
        raise RuntimeError(f"Required image tool is unavailable: {command[0]}") from error
    except subprocess.CalledProcessError as error:
        detail = error.stderr.strip() or error.stdout.strip()
        raise RuntimeError(
            detail or f"{command[0]} failed with status {error.returncode}"
        ) from error
    return result.stdout.strip()


def _escape_wifi_qr_value(value: str) -> str:
    for character in ("\\", ";", ",", ":", '"'):
        value = value.replace(character, f"\\{character}")
    return value


def _write_private_file(path: Path, data: bytes) -> None:
    descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(descriptor, "wb") as output_file:
        output_file.write(data)


if __name__ == "__main__":
    main()

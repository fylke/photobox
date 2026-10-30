import argparse
import json
import os
import secrets
import sys
from io import BytesIO
from pathlib import Path

import qrcode

from photobox.pairing import PairingError, PairingManager, generate_setup_pin, hash_setup_pin


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
        description="Create private, per-device Photobox setup credentials and a Wi-Fi QR."
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        type=Path,
        help="new or empty directory for private per-device provisioning files",
    )
    args = parser.parse_args(argv)
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

    print("Per-device setup credentials created. Record these privately:")
    print(f"Device: {device_id}")
    print(f"Wi-Fi name: {wifi_ssid}")
    print(f"Wi-Fi password: {wifi_password}")
    print(f"Setup PIN: {setup_pin}")
    print(f"Private config and Wi-Fi QR: {output_dir}")
    print("This is not a flashable OS image; the image builder is not implemented yet.")


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
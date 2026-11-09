import json
import os
import re
import tempfile
import uuid
from pathlib import Path

from photobox.provision import load_device_config


def _install_file(path: Path, data: bytes, owner: int, group: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=".photobox-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(data)
            output.flush()
            os.fchmod(output.fileno(), 0o600)
            os.fchown(output.fileno(), owner, group)
            os.fsync(output.fileno())
        os.replace(temporary_name, path)
    finally:
        Path(temporary_name).unlink(missing_ok=True)


def apply_boot_config(boot_config: Path, root: Path, service_uid: int, service_gid: int) -> None:
    data = boot_config.read_bytes()
    config_path = root / "etc/photobox/device.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    if config_path.exists() and json.loads(config_path.read_bytes()) != json.loads(data):
        raise ValueError("A different device configuration is already installed")

    with tempfile.TemporaryDirectory(prefix="photobox-validate-") as temporary_dir:
        validation_path = Path(temporary_dir) / "device.json"
        validation_path.write_bytes(data)
        validation_path.chmod(0o600)
        manifest = load_device_config(validation_path)

    device_id = manifest.get("device_id")
    wifi = manifest["wifi"]
    if not isinstance(device_id, str) or not re.fullmatch(r"[A-F0-9]{8}", device_id):
        raise ValueError("Invalid device ID")
    if not isinstance(wifi, dict):
        raise TypeError("Invalid Wi-Fi settings")
    country = wifi.get("country")
    ssid = wifi.get("ssid")
    password = wifi.get("password")
    if not isinstance(country, str) or not re.fullmatch(r"[A-Z]{2}", country):
        raise ValueError("A Wi-Fi country code is required")
    if ssid != f"Photobox-{device_id}" or not isinstance(password, str) or not re.fullmatch(
        r"[A-Za-z0-9_-]{8,63}", password
    ):
        raise ValueError("Invalid setup hotspot credentials")

    profile = (
        "[connection]\n"
        "id=Photobox setup\n"
        f"uuid={uuid.uuid5(uuid.NAMESPACE_DNS, 'photobox-' + device_id)}\n"
        "type=wifi\nautoconnect=true\nautoconnect-priority=10\ninterface-name=wlan0\n"
        f"\n[wifi]\nmode=ap\nssid={ssid}\nband=bg\n"
        f"\n[wifi-security]\nkey-mgmt=wpa-psk\npsk={password}\n"
        "\n[ipv4]\nmethod=shared\n\n[ipv6]\nmethod=disabled\n"
    ).encode("ascii")
    environment = (
        "PHOTOBOX_DEVICE_CONFIG=/etc/photobox/device.json\n"
        f"PHOTOBOX_WIFI_COUNTRY={country}\n"
    ).encode("ascii")
    _install_file(config_path, data, service_uid, service_gid)
    _install_file(root / "etc/photobox/device.env", environment, 0, 0)
    _install_file(
        root / "etc/NetworkManager/system-connections/photobox-setup.nmconnection",
        profile,
        0,
        0,
    )
    boot_config.unlink()


def main() -> None:
    import pwd

    service_user = pwd.getpwnam("photobox")
    apply_boot_config(
        Path("/boot/firmware/photobox-device.json"), Path("/"), service_user.pw_uid, service_user.pw_gid
    )


if __name__ == "__main__":
    main()
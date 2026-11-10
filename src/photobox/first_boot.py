import os
import re
import sqlite3
import tempfile
from pathlib import Path


def install_bootstrap_profile(root: Path, kernel_command_line: str) -> bool:
    country_codes = re.findall(
        r"(?:^|\s)cfg80211\.ieee80211_regdom=([A-Za-z]{2})(?=\s|$)", kernel_command_line
    )
    environment_path = root / "etc/photobox/device.env"
    if not country_codes and environment_path.is_file():
        environment = environment_path.read_text(encoding="ascii")
        match = re.fullmatch(
            r"PHOTOBOX_BOOTSTRAP=1\nPHOTOBOX_WIFI_COUNTRY=([A-Z]{2})\n", environment
        )
        if match is not None:
            country_codes = [match.group(1)]
    if len(country_codes) != 1:
        return False
    database_path = root / "var/lib/photobox/pairing.sqlite3"
    if database_path.exists():
        try:
            with sqlite3.connect(f"file:{database_path}?mode=ro", uri=True) as connection:
                initialized = connection.execute(
                    "SELECT 1 FROM settings WHERE key = 'setup_initialized'"
                ).fetchone()
        except sqlite3.Error:
            return False
        if initialized is not None:
            return False

    profile = (
        "[connection]\nid=Photobox first boot\n"
        "uuid=1095de0b-9c2c-4e31-b058-9450c10a86bb\n"
        "type=wifi\nautoconnect=true\ninterface-name=wlan0\n"
        "\n[wifi]\nmode=ap\nssid=Photobox Setup\nband=bg\nchannel=1\n"
        "\n[ipv4]\nmethod=shared\n\n[ipv6]\nmethod=disabled\n"
    ).encode("ascii")
    _install_file(
        root / "run/NetworkManager/system-connections/photobox-first-boot.nmconnection",
        profile,
        0,
        0,
    )
    _install_file(
        environment_path,
        f"PHOTOBOX_BOOTSTRAP=1\nPHOTOBOX_WIFI_COUNTRY={country_codes[0].upper()}\n".encode("ascii"),
        0,
        0,
    )
    return True


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


def main() -> None:
    install_bootstrap_profile(Path("/"), Path("/proc/cmdline").read_text())


if __name__ == "__main__":
    main()
import pytest
from dbus_next import Message

from photobox.network import _venue_profile, validate_wifi_credentials


def test_venue_profile_contains_credentials_only_in_dbus_values():
    profile = _venue_profile("Event Guest Wi-Fi", "a private password")

    assert profile["connection"]["type"].value == "wifi"
    assert profile["connection"]["autoconnect"].value is False
    assert profile["wifi"]["ssid"].value == b"Event Guest Wi-Fi"
    assert profile["wifi-security"]["key-mgmt"].value == "wpa-psk"
    assert profile["wifi-security"]["psk"].value == "a private password"
    assert profile["ipv4"]["method"].value == "auto"
    assert profile["ipv6"]["method"].value == "auto"


def test_venue_profile_is_valid_dbus_settings_payload():
    message = Message(
        destination="org.freedesktop.NetworkManager",
        path="/org/freedesktop/NetworkManager/Settings",
        interface="org.freedesktop.NetworkManager.Settings",
        member="AddConnection2",
        signature="a{sa{sv}}ua{sv}",
        body=[_venue_profile("Event Guest Wi-Fi", "a private password"), 1, {}],
    )

    assert message._marshall()


@pytest.mark.parametrize(
    ("ssid", "password"),
    [
        ("", "validpass"),
        ("x" * 33, "validpass"),
        ("wifi", "short"),
        ("wifi", "é" * 32),
    ],
)
def test_invalid_wifi_credentials_are_rejected(ssid, password):
    with pytest.raises(ValueError):
        validate_wifi_credentials(ssid, password)


def test_wifi_credentials_accept_valid_passphrase_and_raw_key():
    validate_wifi_credentials("Booth Wi-Fi", "a valid passphrase")
    validate_wifi_credentials("Booth Wi-Fi", "a" * 64)

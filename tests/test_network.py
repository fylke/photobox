import asyncio

import pytest
from dbus_next import Message, Variant

from photobox.network import (
    NetworkManagerAdapter,
    NetworkStatus,
    _hotspot_profile,
    _venue_profile,
    validate_wifi_credentials,
)


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


def test_private_hotspot_profile_is_valid_dbus_payload():
    profile = _hotspot_profile("Photobox-1234ABCD", "test_password123")
    assert profile["wifi"]["mode"].value == "ap"
    assert profile["wifi-security"]["psk"].value == "test_password123"
    message = Message(
        destination="org.freedesktop.NetworkManager",
        path="/org/freedesktop/NetworkManager/Settings",
        interface="org.freedesktop.NetworkManager.Settings",
        member="AddConnection2",
        signature="a{sa{sv}}ua{sv}",
        body=[profile, 1, {}],
    )
    assert message._marshall()


@pytest.mark.parametrize("recovery", [False, True])
def test_private_hotspot_replaces_bootstrap(monkeypatch, recovery):
    adapter = NetworkManagerAdapter()
    calls = []

    class Bus:
        def disconnect(self):
            calls.append("disconnect")

    async def connect():
        return Bus()

    async def wireless_device(bus):
        return "/wifi"

    async def call(bus, path, interface, method, signature="", body=None):
        calls.append(method)
        if method == "ListConnections":
            return [["/bootstrap"]]
        if method == "GetSettings":
            return [{"connection": {"id": Variant("s", "Photobox first boot")}}]
        if method == "AddConnection2":
            return ["/private", {}]
        if method == "ActivateConnection":
            return ["/private-active"]
        return []

    async def prop(bus, path, interface, name):
        return ["/bootstrap-active"] if name == "ActiveConnections" else "/bootstrap"

    async def activation(bus, active_path):
        return 2

    monkeypatch.setattr(adapter, "_connect", connect)
    monkeypatch.setattr(adapter, "_wireless_device", wireless_device)
    monkeypatch.setattr(adapter, "_call", call)
    monkeypatch.setattr(adapter, "_property", prop)
    monkeypatch.setattr(adapter, "_wait_for_activation", activation)
    asyncio.run(adapter._activate_private_hotspot("Photobox-1234ABCD", "test_password123", recovery))
    assert calls.index("AddConnection2") < calls.index("Delete") < calls.index("ActivateConnection")
    assert "DeactivateConnection" in calls
    assert calls[-1] == "disconnect"


def test_recovery_leaves_existing_network_untouched(monkeypatch):
    adapter = NetworkManagerAdapter()
    calls = []

    class Bus:
        def disconnect(self):
            pass

    async def connect():
        return Bus()

    async def wireless_device(bus):
        return "/wifi"

    async def call(bus, path, interface, method, signature="", body=None):
        calls.append(method)
        if method == "ListConnections":
            return [["/private"]]
        if method == "GetSettings":
            return [{"connection": {"id": Variant("s", "Photobox setup")}}]
        raise AssertionError(method)

    async def wireless_state(bus):
        return NetworkStatus(True, "venue", "Connected", "192.168.1.25"), "192.168.1.25"

    monkeypatch.setattr(adapter, "_connect", connect)
    monkeypatch.setattr(adapter, "_wireless_device", wireless_device)
    monkeypatch.setattr(adapter, "_call", call)
    monkeypatch.setattr(adapter, "_wireless_state", wireless_state)
    asyncio.run(adapter._activate_private_hotspot("Photobox-1234ABCD", "test_password123", True))
    assert calls == ["ListConnections", "GetSettings"]


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

import asyncio
import re
import uuid
from dataclasses import dataclass
from typing import Protocol

from dbus_next import BusType, Message, MessageType, Variant
from dbus_next.aio import MessageBus
from dbus_next.errors import DBusError

_BUS_NAME = "org.freedesktop.NetworkManager"
_ROOT_PATH = "/org/freedesktop/NetworkManager"
_SETTINGS_PATH = f"{_ROOT_PATH}/Settings"
_SETTINGS_INTERFACE = f"{_BUS_NAME}.Settings"
_DEVICE_INTERFACE = f"{_BUS_NAME}.Device"
_ACTIVE_INTERFACE = f"{_BUS_NAME}.Connection.Active"
_CONNECTION_INTERFACE = f"{_BUS_NAME}.Settings.Connection"
_PROPERTIES_INTERFACE = "org.freedesktop.DBus.Properties"
_WIFI_INTERFACE = "wlan0"
_SETUP_CONNECTION_ID = "Photobox setup"
_VENUE_CONNECTION_PREFIX = "Photobox venue "


class NetworkError(RuntimeError):
    pass


@dataclass(frozen=True)
class NetworkStatus:
    available: bool
    mode: str
    message: str
    address: str | None = None

    def as_dict(self) -> dict[str, bool | str | None]:
        return {
            "available": self.available,
            "mode": self.mode,
            "message": self.message,
            "address": self.address,
        }


class NetworkManager(Protocol):
    def status(self) -> NetworkStatus: ...

    def configure_venue(self, ssid: str, password: str) -> NetworkStatus: ...


class DisabledNetworkManager:
    def status(self) -> NetworkStatus:
        return NetworkStatus(False, "disabled", "Network setup is not configured for this host.")

    def configure_venue(self, ssid: str, password: str) -> NetworkStatus:
        raise NetworkError("Network setup is only available on a provisioned Photobox image.")


class NetworkManagerAdapter:
    def status(self) -> NetworkStatus:
        try:
            return asyncio.run(self._status())
        except (DBusError, OSError, TimeoutError):
            return NetworkStatus(
                False,
                "unavailable",
                "NetworkManager is unavailable; the current network was not changed.",
            )

    def configure_venue(self, ssid: str, password: str) -> NetworkStatus:
        validate_wifi_credentials(ssid, password)
        try:
            return asyncio.run(self._configure_venue(ssid, password))
        except DBusError as error:
            raise NetworkError(
                "NetworkManager could not configure Wi-Fi. Check its service and Photobox policy."
            ) from error
        except (OSError, TimeoutError) as error:
            raise NetworkError(
                "NetworkManager could not connect. Check the Wi-Fi details and signal; "
                "the setup network should remain available."
            ) from error

    async def _status(self) -> NetworkStatus:
        bus = await self._connect()
        try:
            try:
                status, address = await self._wireless_state(bus)
            except NetworkError as error:
                return NetworkStatus(True, "offline", str(error))
            return status or NetworkStatus(
                True,
                "offline",
                "No Wi-Fi connection is active; use the setup network or try venue Wi-Fi again.",
                address,
            )
        finally:
            bus.disconnect()

    async def _configure_venue(self, ssid: str, password: str) -> NetworkStatus:
        bus = await self._connect()
        profile_path = None
        verified = False
        try:
            device_path = await self._wireless_device(bus)
            result = await self._call(
                bus,
                _SETTINGS_PATH,
                _SETTINGS_INTERFACE,
                "AddConnection2",
                "a{sa{sv}}ua{sv}",
                [_venue_profile(ssid, password), 1, {}],
            )
            profile_path = result[0]
            profile_settings = await self._call(
                bus,
                profile_path,
                _CONNECTION_INTERFACE,
                "GetSettings",
            )
            active_id = profile_settings[0]["connection"]["id"].value
            active_path = await self._call(
                bus,
                _ROOT_PATH,
                _BUS_NAME,
                "ActivateConnection",
                "ooo",
                [profile_path, device_path, "/"],
            )
            state = await self._wait_for_activation(bus, active_path[0])
            if state != 2:
                raise NetworkError(
                    "NetworkManager could not connect. Check the Wi-Fi details and signal; "
                    "the setup network remains available."
                )

            address, gateway = await self._device_network(bus, device_path)
            if address is None or gateway is None:
                raise NetworkError(
                    "Venue Wi-Fi connected without a usable network address. "
                    "The setup network remains available."
                )

            await self._remove_old_venue_profiles(bus, profile_path)
            await self._set_autoconnect(bus, profile_path, True)
            await self._deactivate_setup_network(bus)
            verified = True
            return NetworkStatus(True, "venue", f"Connected to {active_id}.", address)
        except (DBusError, NetworkError, TimeoutError):
            if profile_path is not None and not verified:
                await self._delete_profile(bus, profile_path)
                await self._restore_setup_network(bus)
            raise
        finally:
            bus.disconnect()

    async def _wireless_state(self, bus: MessageBus) -> tuple[NetworkStatus | None, str | None]:
        device_path = await self._wireless_device(bus)
        active_path = await self._property(bus, device_path, _DEVICE_INTERFACE, "ActiveConnection")
        if active_path == "/":
            return None, None
        state = await self._property(bus, active_path, _ACTIVE_INTERFACE, "State")
        if state != 2:
            return None, None
        connection_path = await self._property(bus, active_path, _ACTIVE_INTERFACE, "Connection")
        settings = await self._call(
            bus,
            connection_path,
            _CONNECTION_INTERFACE,
            "GetSettings",
        )
        connection_id = settings[0]["connection"]["id"].value
        address, _ = await self._device_network(bus, device_path)
        if connection_id == _SETUP_CONNECTION_ID:
            return (
                NetworkStatus(True, "setup", "Connected to the Photobox setup network.", address),
                address,
            )
        if connection_id.startswith(_VENUE_CONNECTION_PREFIX):
            return (
                NetworkStatus(True, "venue", "Connected to venue Wi-Fi.", address),
                address,
            )
        return NetworkStatus(True, "other", "Connected to another Wi-Fi network.", address), address

    async def _connect(self) -> MessageBus:
        return await asyncio.wait_for(
            MessageBus(bus_type=BusType.SYSTEM).connect(),
            timeout=5,
        )

    async def _call(
        self,
        bus: MessageBus,
        path: str,
        interface: str,
        method: str,
        signature: str = "",
        body: list[object] | None = None,
    ) -> list[object]:
        reply = await asyncio.wait_for(
            bus.call(
                Message(
                    destination=_BUS_NAME,
                    path=path,
                    interface=interface,
                    member=method,
                    signature=signature,
                    body=body or [],
                )
            ),
            timeout=10,
        )
        if reply.message_type == MessageType.ERROR:
            message = str(reply.body[0]) if reply.body else "NetworkManager D-Bus request failed."
            raise DBusError(reply.error_name or "org.freedesktop.DBus.Error.Failed", message)
        return reply.body

    async def _property(self, bus: MessageBus, path: str, interface: str, name: str):
        body = await self._call(
            bus,
            path,
            _PROPERTIES_INTERFACE,
            "Get",
            "ss",
            [interface, name],
        )
        return body[0].value

    async def _wireless_device(self, bus: MessageBus) -> str:
        devices = await self._call(bus, _ROOT_PATH, _BUS_NAME, "GetDevices")
        for path in devices[0]:
            device_type = await self._property(bus, path, _DEVICE_INTERFACE, "DeviceType")
            interface = await self._property(bus, path, _DEVICE_INTERFACE, "Interface")
            if device_type == 2 and interface == _WIFI_INTERFACE:
                return path
        raise NetworkError("No Wi-Fi device named wlan0 is available.")

    async def _wait_for_activation(self, bus: MessageBus, active_path: str) -> int:
        for _ in range(80):
            state = await self._property(bus, active_path, _ACTIVE_INTERFACE, "State")
            if state in (2, 4):
                return state
            await asyncio.sleep(0.25)
        return 0

    async def _device_network(
        self, bus: MessageBus, device_path: str
    ) -> tuple[str | None, str | None]:
        config_path = await self._property(bus, device_path, _DEVICE_INTERFACE, "Ip4Config")
        if config_path == "/":
            return None, None
        addresses = await self._property(bus, config_path, f"{_BUS_NAME}.IP4Config", "AddressData")
        gateway_value = await self._property(bus, config_path, f"{_BUS_NAME}.IP4Config", "Gateway")
        address = addresses[0]["address"].value if addresses else None
        gateway = gateway_value or None
        return address, gateway

    async def _deactivate_setup_network(self, bus: MessageBus) -> None:
        active_paths = await self._property(bus, _ROOT_PATH, _BUS_NAME, "ActiveConnections")
        for active_path in active_paths:
            connection_path = await self._property(
                bus, active_path, _ACTIVE_INTERFACE, "Connection"
            )
            settings = await self._call(
                bus,
                connection_path,
                _CONNECTION_INTERFACE,
                "GetSettings",
            )
            connection_id = settings[0]["connection"]["id"].value
            if connection_id == _SETUP_CONNECTION_ID:
                await self._call(
                    bus,
                    _ROOT_PATH,
                    _BUS_NAME,
                    "DeactivateConnection",
                    "o",
                    [active_path],
                )

    async def _restore_setup_network(self, bus: MessageBus) -> None:
        device_path = await self._wireless_device(bus)
        active_path = await self._property(bus, device_path, _DEVICE_INTERFACE, "ActiveConnection")
        if active_path != "/":
            connection_path = await self._property(
                bus, active_path, _ACTIVE_INTERFACE, "Connection"
            )
            settings = await self._call(
                bus,
                connection_path,
                _CONNECTION_INTERFACE,
                "GetSettings",
            )
            if settings[0]["connection"]["id"].value == _SETUP_CONNECTION_ID:
                state = await self._property(bus, active_path, _ACTIVE_INTERFACE, "State")
                address, _ = await self._device_network(bus, device_path)
                if state == 2 and address is not None:
                    return

        profiles = await self._call(bus, _SETTINGS_PATH, _SETTINGS_INTERFACE, "ListConnections")
        for profile_path in profiles[0]:
            settings = await self._call(
                bus,
                profile_path,
                _CONNECTION_INTERFACE,
                "GetSettings",
            )
            if settings[0]["connection"]["id"].value == _SETUP_CONNECTION_ID:
                active_path = await self._call(
                    bus,
                    _ROOT_PATH,
                    _BUS_NAME,
                    "ActivateConnection",
                    "ooo",
                    [profile_path, device_path, "/"],
                )
                state = await self._wait_for_activation(bus, active_path[0])
                if state != 2:
                    raise NetworkError(
                        "Venue Wi-Fi failed and the setup network could not be restored; "
                        "reboot the Pi."
                    )
                address, _ = await self._device_network(bus, device_path)
                if address is None:
                    raise NetworkError(
                        "Venue Wi-Fi failed and the setup network has no address; reboot the Pi."
                    )
                return
        raise NetworkError(
            "Venue Wi-Fi failed and the setup network could not be restored; reboot the Pi."
        )

    async def _remove_old_venue_profiles(self, bus: MessageBus, keep_path: str) -> None:
        profiles = await self._call(bus, _SETTINGS_PATH, _SETTINGS_INTERFACE, "ListConnections")
        for profile_path in profiles[0]:
            if profile_path == keep_path:
                continue
            settings = await self._call(
                bus,
                profile_path,
                _CONNECTION_INTERFACE,
                "GetSettings",
            )
            connection_id = settings[0]["connection"]["id"].value
            if connection_id.startswith(_VENUE_CONNECTION_PREFIX):
                await self._delete_profile(bus, profile_path)

    async def _set_autoconnect(self, bus: MessageBus, profile_path: str, enabled: bool) -> None:
        settings = await self._call(
            bus,
            profile_path,
            _CONNECTION_INTERFACE,
            "GetSettings",
        )
        profile = settings[0]
        profile["connection"]["autoconnect"] = Variant("b", enabled)
        await self._call(
            bus,
            profile_path,
            _CONNECTION_INTERFACE,
            "Update2",
            "a{sa{sv}}ua{sv}",
            [profile, 1, {}],
        )

    async def _delete_profile(self, bus: MessageBus, profile_path: str) -> None:
        await self._call(bus, profile_path, _CONNECTION_INTERFACE, "Delete")


def validate_wifi_credentials(ssid: str, password: str) -> None:
    if not ssid or len(ssid.encode("utf-8")) > 32 or not ssid.isprintable():
        raise ValueError("Wi-Fi name must be between 1 and 32 UTF-8 bytes.")
    if len(password) == 64 and re.fullmatch(r"[A-Fa-f0-9]{64}", password):
        return
    if not password.isprintable() or not 8 <= len(password.encode("utf-8")) <= 63:
        raise ValueError("Wi-Fi password must be 8–63 bytes, or a 64-digit hexadecimal key.")


def _venue_profile(ssid: str, password: str) -> dict[str, dict[str, Variant]]:
    profile_uuid = str(uuid.uuid4())
    return {
        "connection": {
            "id": Variant("s", _VENUE_CONNECTION_PREFIX + profile_uuid[:8]),
            "uuid": Variant("s", profile_uuid),
            "type": Variant("s", "wifi"),
            "autoconnect": Variant("b", False),
            "autoconnect-priority": Variant("i", 20),
            "interface-name": Variant("s", _WIFI_INTERFACE),
        },
        "wifi": {
            "mode": Variant("s", "infrastructure"),
            "ssid": Variant("ay", ssid.encode("utf-8")),
        },
        "wifi-security": {
            "key-mgmt": Variant("s", "wpa-psk"),
            "psk": Variant("s", password),
        },
        "ipv4": {"method": Variant("s", "auto")},
        "ipv6": {"method": Variant("s", "auto")},
    }

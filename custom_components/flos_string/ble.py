"""The Bluetooth connection to one Flos String Light.

One connection per lamp, open for as long as the config entry is loaded:

- The lamp's indications on the brightness characteristic are the state. It sends
  one with the current level right after the subscription, and none after a write
  of our own, so every write is followed by a read.
- Every REFRESH_INTERVAL the brightness is read over the open connection, as a
  safety net for an indication that never came.
- When the connection drops, the lamp is unavailable at once and a background task
  reconnects: after 5, 10 and 30 seconds, then every minute, and sooner when the
  lamp is seen advertising again.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
import contextlib
import logging
import time

from bleak import BleakClient, BleakError
from bleak.backends.characteristic import BleakGATTCharacteristic
from bleak_retry_connector import BleakClientWithServiceCache, establish_connection

from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.core import CALLBACK_TYPE, Event, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError

from .const import (
    BRIGHTNESS_CHAR_UUID,
    CONNECT_ATTEMPTS,
    DOMAIN,
    RECONNECT_BACKOFF,
    REFRESH_INTERVAL,
    STABLE_CONNECTION,
)

_LOGGER = logging.getLogger(__name__)

# What a Bluetooth operation raises when the lamp or the adapter lets go.
BLE_ERRORS = (BleakError, TimeoutError, OSError, EOFError)


def _describe(value: bytes) -> str:
    """Hex plus printable ASCII, for the GATT table in the debug log."""
    text = "".join(chr(b) if 32 <= b < 127 else "." for b in value)
    return f"{value.hex()} '{text}'"


class FlosStringBLEManager:
    """Keep the connection to one lamp open, and read and write over it."""

    def __init__(self, hass: HomeAssistant, address: str) -> None:
        """Initialize the manager; async_start() opens the connection."""
        self._hass = hass
        self.address = address
        # 0-100 as the lamp reports it; None until the first read.
        self.brightness: int | None = None
        self._client: BleakClient | None = None
        # True once the connection is subscribed and the brightness is read.
        self._ready = False
        # Serializes everything that talks to the lamp.
        self._lock = asyncio.Lock()
        self._listeners: set[Callable[[], None]] = set()
        self._task: asyncio.Task[None] | None = None
        self._advertised = asyncio.Event()
        self._disconnected = asyncio.Event()
        self._stopped = False
        self._outage_logged = False
        self._gatt_logged = False

    @property
    def available(self) -> bool:
        """Return True while the lamp is connected and its state is known."""
        return self._ready

    @callback
    def async_add_listener(self, listener: Callable[[], None]) -> CALLBACK_TYPE:
        """Call listener on every change of brightness or availability."""
        self._listeners.add(listener)
        return lambda: self._listeners.discard(listener)

    @callback
    def _notify(self) -> None:
        for listener in list(self._listeners):
            listener()

    # ------------------------------------------------------------------ lifecycle

    @callback
    def async_start(self, entry: ConfigEntry) -> None:
        """Connect in the background, so the setup never waits for the lamp."""
        entry.async_on_unload(
            bluetooth.async_register_callback(
                self._hass,
                self._on_advertisement,
                bluetooth.BluetoothCallbackMatcher(
                    address=self.address, connectable=True
                ),
                bluetooth.BluetoothScanningMode.ACTIVE,
            )
        )
        entry.async_on_unload(
            self._hass.bus.async_listen_once(
                EVENT_HOMEASSISTANT_STOP, self._on_hass_stop
            )
        )
        self._task = entry.async_create_background_task(
            self._hass, self._run(), f"{DOMAIN} connection {self.address}"
        )

    async def async_stop(self) -> None:
        """Disconnect for good: on unload and when Home Assistant stops."""
        self._stopped = True
        if (task := self._task) is not None:
            # Cancel the reconnect loop first, so it cannot connect again.
            self._task = None
            task.cancel()
            await asyncio.wait([task])
        if (client := self._client) is not None:
            await self._disconnect(client)

    async def _on_hass_stop(self, _event: Event) -> None:
        await self.async_stop()

    @callback
    def _on_advertisement(
        self,
        _service_info: bluetooth.BluetoothServiceInfoBleak,
        _change: bluetooth.BluetoothChange,
    ) -> None:
        """The lamp advertises (it does not while connected): cut the wait short."""
        self._advertised.set()

    # ----------------------------------------------------------- connection loop

    async def _run(self) -> None:
        """Connect, stay connected and reconnect until the task is cancelled."""
        step = 0  # position in RECONNECT_BACKOFF since the last stable connection
        while True:
            self._advertised.clear()
            try:
                await self._connect()
            except BLE_ERRORS as err:
                # Once at info level per outage; a lamp without power fails for days.
                _LOGGER.log(
                    logging.DEBUG if self._outage_logged else logging.INFO,
                    "Flos String Light %s is not reachable: %s",
                    self.address,
                    err,
                )
                self._outage_logged = True
            except Exception:  # noqa: BLE001 - a bug must not end the reconnect loop
                _LOGGER.exception("Unexpected error connecting to %s", self.address)
            else:
                connected_at = time.monotonic()
                await self._hold()
                if time.monotonic() - connected_at >= STABLE_CONNECTION:
                    step = 0
            delay = RECONNECT_BACKOFF[min(step, len(RECONNECT_BACKOFF) - 1)]
            step += 1
            await self._wait_before_retry(delay)

    async def _wait_before_retry(self, delay: float) -> None:
        """Wait delay seconds, or less when the lamp advertises in the meantime.

        Never less than the first backoff step: a lamp that advertises but refuses
        the connection must not be retried in a tight loop.
        """
        floor = RECONNECT_BACKOFF[0]
        await asyncio.sleep(floor)
        if delay > floor:
            with contextlib.suppress(TimeoutError):
                async with asyncio.timeout(delay - floor):
                    await self._advertised.wait()

    async def _connect(self) -> None:
        """Open the connection, subscribe to the indications and read the state."""
        ble_device = bluetooth.async_ble_device_from_address(
            self._hass, self.address, connectable=True
        )
        if ble_device is None:
            raise BleakError("no connectable Bluetooth adapter or proxy sees the lamp")

        _LOGGER.debug("Connecting to Flos String Light %s", self.address)
        self._disconnected.clear()
        client = await establish_connection(
            BleakClientWithServiceCache,
            ble_device,
            self.address,
            disconnected_callback=self._on_disconnected,
            max_attempts=CONNECT_ATTEMPTS,
            # Between attempts the lamp may have become reachable over another path.
            ble_device_callback=lambda: (
                bluetooth.async_ble_device_from_address(
                    self._hass, self.address, connectable=True
                )
                or ble_device
            ),
        )
        self._client = client
        try:
            async with self._lock:
                await self._log_gatt_table(client)
                # Without bonding the CCCD is back at 0000 on every connection, so
                # subscribe every time. start_notify() writes the CCCD itself.
                await client.start_notify(BRIGHTNESS_CHAR_UUID, self._on_indication)
                # Read only now: before the subscription the lamp has been seen to
                # answer 0 while it was at 100 %.
                data = await client.read_gatt_char(BRIGHTNESS_CHAR_UUID)
        except Exception:
            await self._disconnect(client)
            raise
        if self._client is not client:
            raise BleakError("the lamp disconnected during the setup")

        self._ready = True
        self._outage_logged = False
        _LOGGER.info("Connected to Flos String Light %s", self.address)
        self._set_brightness(data, "Read")

    async def _hold(self) -> None:
        """Return when the connection is gone; until then, refresh now and then."""
        while True:
            try:
                async with asyncio.timeout(REFRESH_INTERVAL):
                    await self._disconnected.wait()
            except TimeoutError:
                await self._refresh()
            else:
                return

    async def _refresh(self) -> None:
        """Read the brightness over the open connection (the safety net)."""
        async with self._lock:
            if (client := self._client) is None:
                return
            try:
                data = await client.read_gatt_char(BRIGHTNESS_CHAR_UUID)
            except BLE_ERRORS as err:
                _LOGGER.debug(
                    "Reading %s failed, reconnecting: %s", self.address, err
                )
                await self._disconnect(client)
                return
        self._set_brightness(data, "Read")

    async def _disconnect(self, client: BleakClient) -> None:
        """Close the connection, also when the lamp no longer answers."""
        with contextlib.suppress(*BLE_ERRORS):
            await client.disconnect()
        # In case the disconnect did not report itself.
        self._on_disconnected(client)

    @callback
    def _on_disconnected(self, client: BleakClient) -> None:
        """Forget the connection; the loop in _run() opens the next one."""
        if client is not self._client:
            return  # an earlier connection, already handled
        self._client = None
        self._disconnected.set()
        if not self._ready:
            return
        self._ready = False
        if not self._stopped:
            _LOGGER.info("Flos String Light %s disconnected", self.address)
            self._outage_logged = True
        self._notify()

    # ------------------------------------------------------------------ brightness

    async def async_set_brightness(self, value: int) -> None:
        """Write the brightness (0-100, 0 is off) and read it back."""
        async with self._lock:
            client = self._client
            if client is None or not self._ready:
                raise HomeAssistantError(
                    translation_domain=DOMAIN, translation_key="not_connected"
                )
            _LOGGER.debug(
                "Writing brightness %d (0x%02X) to %s", value, value, self.address
            )
            try:
                await client.write_gatt_char(
                    BRIGHTNESS_CHAR_UUID, bytes([value]), response=True
                )
                # The lamp sends no indication after a write of our own.
                data = await client.read_gatt_char(BRIGHTNESS_CHAR_UUID)
            except BLE_ERRORS as err:
                # A fresh connection is the way back to a known state.
                await self._disconnect(client)
                raise HomeAssistantError(
                    translation_domain=DOMAIN,
                    translation_key="command_failed",
                    translation_placeholders={"error": str(err)},
                ) from err
        self._set_brightness(data, "Read")

    @callback
    def _on_indication(
        self, _characteristic: BleakGATTCharacteristic, data: bytearray
    ) -> None:
        """The lamp reports its brightness."""
        self._set_brightness(bytes(data), "Indication:")

    @callback
    def _set_brightness(self, data: bytes, source: str) -> None:
        if not data:
            return
        _LOGGER.debug(
            "%s brightness %d (0x%02X) from %s", source, data[0], data[0], self.address
        )
        self.brightness = data[0]
        self._notify()

    # ----------------------------------------------------------------- diagnostics

    async def _log_gatt_table(self, client: BleakClient) -> None:
        """Log every service, characteristic and descriptor with its value.

        Diagnostics only: reads, never writes. Runs once per manager (once per
        Home Assistant start or entry reload), and only with debug logging on.
        """
        if self._gatt_logged or not _LOGGER.isEnabledFor(logging.DEBUG):
            return
        self._gatt_logged = True
        for service in client.services:
            _LOGGER.debug(
                "GATT %s: service %s (handle %d)",
                self.address,
                service.uuid,
                service.handle,
            )
            for char in service.characteristics:
                value = "-"
                if "read" in char.properties:
                    try:
                        value = _describe(bytes(await client.read_gatt_char(char)))
                    except (BleakError, TimeoutError, ValueError) as err:
                        value = f"read failed: {err}"
                _LOGGER.debug(
                    "GATT %s:   characteristic %s (handle %d) %s: %s",
                    self.address,
                    char.uuid,
                    char.handle,
                    char.properties,
                    value,
                )
                for descriptor in char.descriptors:
                    try:
                        value = _describe(
                            bytes(await client.read_gatt_descriptor(descriptor.handle))
                        )
                    except (BleakError, TimeoutError, ValueError) as err:
                        value = f"read failed: {err}"
                    _LOGGER.debug(
                        "GATT %s:     descriptor %s (handle %d): %s",
                        self.address,
                        descriptor.uuid,
                        descriptor.handle,
                        value,
                    )

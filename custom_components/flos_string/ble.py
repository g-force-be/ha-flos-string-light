"""The Bluetooth connection to one Flos String Light.

One connection per lamp, open for as long as the config entry is loaded:

- The lamp's indications on the brightness characteristic are the state. It sends
  one with the current level right after the subscription, and none after a write
  of our own, so every write is followed by a read.
- Every REFRESH_INTERVAL the brightness is read over the open connection, as a
  safety net for an indication that never came.
- The lamp's name is read on every connection, and can be written.
- When the connection drops, the lamp is unavailable at once and a background task
  reconnects: after 5, 10 and 30 seconds, then every minute, and sooner when the
  lamp is seen advertising again.

Or, as an option per lamp, a connection only when it is needed ("on demand"):

- A change connects, writes, reads back and disconnects. So does a read of the
  state: at the start, every poll interval and when the lamp advertises again.
- All lamps that connect on demand take turns, so that no two are connected at
  once. A connection made while the Bluetooth proxy holds another lamp reaches a
  lamp that reads a brightness back without carrying it out.
- A lamp that is not connected advertises. One that stops advertising has no
  power: it is unavailable, and nothing connects to it until it advertises again.
  That is checked every power check interval, without a connection.
- At the same moments the manager notes which Bluetooth proxy hears the lamp
  best and how well: the path Home Assistant takes for the next connection.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
import contextlib
import logging
import time

from bleak import BleakClient, BleakError
from bleak.backends.characteristic import BleakGATTCharacteristic
from bleak.backends.device import BLEDevice
from bleak_retry_connector import BleakClientWithServiceCache, establish_connection

from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.core import CALLBACK_TYPE, Event, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError

from .const import (
    BRIGHTNESS_CHAR_UUID,
    CONNECT_ATTEMPTS,
    DEVICE_NAME_CHAR_UUID,
    DOMAIN,
    NAME_CHAR_UUID,
    NAME_LENGTH,
    NAME_READBACK_ATTEMPTS,
    NAME_READBACK_INTERVAL,
    RECONNECT_BACKOFF,
    REFRESH_INTERVAL,
    STABLE_CONNECTION,
)
from .util import clean_name

_LOGGER = logging.getLogger(__name__)

# What a Bluetooth operation raises when the lamp or the adapter lets go.
BLE_ERRORS = (BleakError, TimeoutError, OSError, EOFError)

# Key in hass.data of the lock that the lamps connecting on demand share.
DATA_TURN = f"{DOMAIN}_turn"


def _describe(value: bytes) -> str:
    """Hex plus printable ASCII, for the GATT table in the debug log."""
    text = "".join(chr(b) if 32 <= b < 127 else "." for b in value)
    return f"{value.hex()} '{text}'"


class FlosStringBLEManager:
    """The connection to one lamp, kept open or made on demand."""

    def __init__(
        self,
        hass: HomeAssistant,
        address: str,
        *,
        on_demand: bool = False,
        poll_interval: float = REFRESH_INTERVAL,
        power_check_interval: float = 0,
    ) -> None:
        """Initialize the manager; async_start() opens the connection.

        on_demand: connect only for a change or a read, and disconnect after it.
        poll_interval: seconds between reads on demand; 0 is never.
        power_check_interval: seconds between checks, on demand, that the lamp
        still advertises; 0 leaves it to Home Assistant, which takes minutes.
        """
        self._hass = hass
        self.address = address
        self.on_demand = on_demand
        self._poll_interval = poll_interval
        self._power_check_interval = power_check_interval
        # On demand: True once the state is read; False after a connection that
        # failed and when the lamp stops advertising.
        self._reachable = False
        # On demand: when the last connection attempt ended, and when the last
        # connection that was made ended; set when the loop has to look again.
        self._last_visit = 0.0
        self._last_contact = 0.0
        self._wake = asyncio.Event()
        # On demand: the Bluetooth adapter or proxy that hears the lamp best, and
        # its signal in dBm; None when none hears it.
        self.proxy: str | None = None
        self.rssi: int | None = None
        # 0-100 as the lamp reports it; None until the first read.
        self.brightness: int | None = None
        # The lamp's own name, without its NUL padding; None when it cannot be read.
        self.name: str | None = None
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
        # Set by async_reconnect(): the next connection is opened without backoff.
        self._reconnect_requested = False

    @property
    def available(self) -> bool:
        """Return True while the lamp is connected and its state is known.

        On demand the lamp is not connected: True while it can be reached.
        """
        return self._reachable if self.on_demand else self._ready

    @callback
    def async_add_listener(self, listener: Callable[[], None]) -> CALLBACK_TYPE:
        """Call listener on every change of brightness, name or availability."""
        self._listeners.add(listener)
        return lambda: self._listeners.discard(listener)

    @callback
    def _notify(self) -> None:
        for listener in list(self._listeners):
            try:
                listener()
            except Exception:  # noqa: BLE001 - an entity's bug must not cost the connection
                _LOGGER.exception("Error updating an entity of %s", self.address)

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
        if self.on_demand:
            entry.async_on_unload(
                bluetooth.async_track_unavailable(
                    self._hass, self._on_unavailable, self.address, connectable=True
                )
            )
        self._task = entry.async_create_background_task(
            self._hass,
            self._run_on_demand() if self.on_demand else self._run(),
            f"{DOMAIN} connection {self.address}",
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
        self._wake.set()

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
                if self._reconnect_requested:
                    # Asked for, and the lamp was there a moment ago: no backoff.
                    self._reconnect_requested = False
                    step = 0
                    continue
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
        # Every connection is opened, closed and opened again before it is used.
        # Home Assistant remembers the lamp's services, but forgets them when it
        # restarts and when the Bluetooth proxy reconnects. A connection that has
        # to look them up is no good: the lamp accepts a brightness and reads it
        # back without carrying it out, or the connection stalls. The one opened
        # right after it uses the remembered services and works. Which kind a
        # connection is cannot be seen from here, so the first is never used.
        client = await self._establish(ble_device)
        _LOGGER.debug("Reached %s: reconnecting before use", self.address)
        await self._disconnect(client)
        client = await self._establish(ble_device)
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
                name = await self._read_name(client)
        except Exception:
            await self._disconnect(client)
            raise
        if self._client is not client:
            raise BleakError("the lamp disconnected during the setup")

        self._ready = True
        self._outage_logged = False
        # On demand this happens every poll interval: not worth a line at info.
        _LOGGER.log(
            logging.DEBUG if self.on_demand else logging.INFO,
            "Connected to Flos String Light %s",
            self.address,
        )
        self.name = name
        self._set_brightness(data, "Read")

    async def _establish(self, ble_device: BLEDevice) -> BleakClient:
        """Open one connection through the Home Assistant Bluetooth stack."""
        return await establish_connection(
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
        if self.on_demand:
            return  # every connection on demand ends like this
        if not self._stopped:
            _LOGGER.info("Flos String Light %s disconnected", self.address)
            self._outage_logged = True
        self._notify()

    # ------------------------------------------------------------------ on demand

    async def _run_on_demand(self) -> None:
        """Read the state at the start, every poll interval and when the lamp is back.

        In between, check every power check interval that the lamp still advertises.
        """
        step = 0  # position in RECONNECT_BACKOFF since the lamp was last reached
        retry_at = 0.0  # after a connection that failed: no new one before this
        while True:
            self._wake.clear()
            self._update_signal()
            now = time.monotonic()
            # Seconds until there may be something to do.
            waits = [self._power_check_interval] if self._power_check_interval else []
            if not self._advertising():
                # No power. Nothing connects until the lamp advertises again.
                self._set_reachable(False, "the lamp does not advertise")
                step, retry_at = 0, 0.0
            elif self._reachable and not self._poll_interval:
                pass  # no polling: the state is what was last read or set
            elif self._reachable and now < self._last_visit + self._poll_interval:
                waits.append(self._last_visit + self._poll_interval - now)
            elif not self._reachable and now < retry_at:
                waits.append(retry_at - now)
            else:
                try:
                    await self._visit()
                except HomeAssistantError:
                    pass  # _visit() logged it, and the lamp is unavailable
                except Exception:  # noqa: BLE001 - a bug must not end the loop
                    _LOGGER.exception("Unexpected error reading %s", self.address)
                    self._set_reachable(False, "unexpected error")
                if self._reachable:
                    step = 0
                else:
                    delay = RECONNECT_BACKOFF[min(step, len(RECONNECT_BACKOFF) - 1)]
                    step += 1
                    retry_at = time.monotonic() + delay
                continue
            with contextlib.suppress(TimeoutError):
                async with asyncio.timeout(min(waits) if waits else None):
                    await self._wake.wait()

    def _advertising(self) -> bool:
        """Return True when the lamp was heard advertising lately: it has power.

        Home Assistant keeps the time of the last advertisement it received; no
        connection is needed. The lamp is silent while it is connected, so the end
        of the last connection counts as well.
        """
        heard = [
            info.time
            for connectable in (True, False)
            if (
                info := bluetooth.async_last_service_info(
                    self._hass, self.address, connectable=connectable
                )
            )
            is not None
        ]
        if not heard:
            return False  # Home Assistant has not heard it, or forgot it
        if not self._power_check_interval:
            return True  # Home Assistant forgets a silent lamp after some minutes
        silence = time.monotonic() - max(*heard, self._last_contact)
        _LOGGER.debug(
            "Flos String Light %s last advertised %.0f s ago", self.address, silence
        )
        return silence <= self._power_check_interval

    @callback
    def _update_signal(self) -> None:
        """Note which proxy hears the lamp best, and how well. No connection.

        Home Assistant connects through the path with the best signal that has
        a free slot; a path that failed lately counts a little less.
        """
        paths = bluetooth.async_scanner_devices_by_address(
            self._hass, self.address, connectable=True
        )
        best = max(paths, key=lambda path: path.advertisement.rssi, default=None)
        proxy, rssi = (
            (best.scanner.name, best.advertisement.rssi) if best else (None, None)
        )
        if (proxy, rssi) != (self.proxy, self.rssi):
            self.proxy, self.rssi = proxy, rssi
            self._notify()

    async def _visit(self, action: Callable[[], Awaitable[None]] | None = None) -> None:
        """Connect, read the state, do one thing and disconnect.

        All lamps share one lock for this, so they take turns: a connection made
        while the Bluetooth proxy holds another lamp reaches a lamp that reads a
        brightness back without carrying it out.
        """
        async with self._hass.data.setdefault(DATA_TURN, asyncio.Lock()):
            if self._stopped:
                raise HomeAssistantError(
                    translation_domain=DOMAIN, translation_key="not_connected"
                )
            try:
                await self._connect()
            except BLE_ERRORS as err:
                self._last_visit = time.monotonic()
                self._set_reachable(False, str(err))
                raise HomeAssistantError(
                    translation_domain=DOMAIN,
                    translation_key="not_reachable",
                    translation_placeholders={"error": str(err)},
                ) from err
            try:
                self._set_reachable(True)
                if action is not None:
                    await action()
            finally:
                if (client := self._client) is not None:
                    await self._disconnect(client)
                self._last_visit = self._last_contact = time.monotonic()

    @callback
    def _set_reachable(self, reachable: bool, reason: str = "") -> None:
        """Keep track of whether the lamp can be reached; that is its availability."""
        if not reachable:
            # Once at info level per outage; a lamp without power fails for days.
            _LOGGER.log(
                logging.DEBUG if self._outage_logged else logging.INFO,
                "Flos String Light %s is not reachable: %s",
                self.address,
                reason,
            )
            self._outage_logged = True
        if reachable == self._reachable:
            return
        self._reachable = reachable
        if reachable:
            _LOGGER.info("Flos String Light %s is reachable", self.address)
        else:
            self._wake.set()  # the loop in _run_on_demand() takes over
        self._notify()

    @callback
    def _on_unavailable(
        self, _service_info: bluetooth.BluetoothServiceInfoBleak
    ) -> None:
        """Home Assistant no longer sees the lamp advertise: it has no power."""
        self._set_reachable(False, "the lamp stopped advertising")

    async def async_refresh(self) -> None:
        """On demand: connect, read the state and disconnect."""
        await self._visit()

    # --------------------------------------------------------------- stay connected

    async def async_reconnect(self) -> None:
        """Close the connection; the loop in _run() opens a new one at once."""
        async with self._lock:
            client = self._client
            if client is None or not self._ready:
                raise HomeAssistantError(
                    translation_domain=DOMAIN, translation_key="not_connected"
                )
            _LOGGER.debug("Reconnecting to %s on request", self.address)
            self._reconnect_requested = True
            await self._disconnect(client)

    # ------------------------------------------------------------------ brightness

    async def async_set_brightness(self, value: int) -> None:
        """Write the brightness (0-100, 0 is off) and read it back."""
        if self.on_demand:
            await self._visit(lambda: self._write_brightness(value))
        else:
            await self._write_brightness(value)

    async def _write_brightness(self, value: int) -> None:
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

    # ------------------------------------------------------------------------ name

    async def async_set_name(self, name: str) -> None:
        """Write the lamp's name and read it back.

        The lamp stores NAME_LENGTH bytes of UTF-8, so bytes are counted, not
        characters. It copies the name to its Device Name a moment later.
        """
        name = clean_name(name)
        encoded = name.encode("utf-8")
        if not encoded:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="name_empty"
            )
        if len(encoded) > NAME_LENGTH:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="name_too_long",
                translation_placeholders={
                    "length": str(len(encoded)),
                    "max": str(NAME_LENGTH),
                },
            )
        if self.on_demand:
            await self._visit(lambda: self._write_name(name, encoded))
        else:
            await self._write_name(name, encoded)

    async def _write_name(self, name: str, encoded: bytes) -> None:
        async with self._lock:
            client = self._client
            if client is None or not self._ready:
                raise HomeAssistantError(
                    translation_domain=DOMAIN, translation_key="not_connected"
                )
            _LOGGER.debug("Writing name %r to %s", encoded, self.address)
            try:
                await client.write_gatt_char(
                    NAME_CHAR_UUID, encoded.ljust(NAME_LENGTH, b"\x00"), response=True
                )
            except BLE_ERRORS as err:
                await self._disconnect(client)
                raise HomeAssistantError(
                    translation_domain=DOMAIN,
                    translation_key="command_failed",
                    translation_placeholders={"error": str(err)},
                ) from err
            # Read the Device Name until it shows the new name; give up when it
            # cannot be read, and settle for what it says after the last try.
            for _ in range(NAME_READBACK_ATTEMPTS):
                await asyncio.sleep(NAME_READBACK_INTERVAL)
                self.name = await self._read_name(client)
                if self.name is None or self.name == name:
                    break
        self._notify()

    async def _read_name(self, client: BleakClient) -> str | None:
        """Read the Device Name; None when the adapter does not pass it on.

        Some Bluetooth stacks keep the Generic Access service to themselves.
        """
        try:
            data = await client.read_gatt_char(DEVICE_NAME_CHAR_UUID)
        except BLE_ERRORS as err:
            _LOGGER.debug("Could not read the name of %s: %s", self.address, err)
            return None
        name = clean_name(bytes(data).decode("utf-8", errors="replace"))
        _LOGGER.debug("Read name %r from %s", name, self.address)
        return name

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

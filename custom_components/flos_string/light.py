"""Light platform for Flos String Light."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from bleak import BleakClient, BleakError
from bleak.exc import BleakDeviceNotFoundError
from bleak_retry_connector import establish_connection, BleakClientWithServiceCache

from homeassistant.components import bluetooth
from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ColorMode,
    LightEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from datetime import timedelta

from .const import (
    ALT_CHAR_UUID,
    BRIGHTNESS_CHAR_UUID,
    CONNECT_TIMEOUT,
    DEFAULT_BRIGHTNESS_PCT,
    DISCONNECT_DELAY,
    DOMAIN,
    MAX_RETRIES,
    SCAN_INTERVAL_SECONDS,
    SERVICE_UUID,
)

_LOGGER = logging.getLogger(__name__)

# HA polls entities at this interval
SCAN_INTERVAL = timedelta(seconds=SCAN_INTERVAL_SECONDS)


def ha_to_flos(ha_brightness: int) -> int:
    """Convert HA brightness (0-255) to Flos brightness (0-100).

    Returns minimum 1 since 0 means OFF on the device.
    """
    return max(1, round(ha_brightness * 100 / 255))


def flos_to_ha(flos_brightness: int) -> int:
    """Convert Flos brightness (0-100) to HA brightness (0-255)."""
    return round(flos_brightness * 255 / 100)


class FlosStringBLEManager:
    """Manage BLE connection to a Flos String Light.

    Uses connect-per-command with delayed disconnect:
    - Connect when a command needs to be sent
    - Schedule disconnect after DISCONNECT_DELAY seconds of inactivity
    - Reuse connection if another command arrives before disconnect
    - Serialize all operations with asyncio.Lock
    """

    def __init__(self, hass: HomeAssistant, address: str) -> None:
        """Initialize the BLE manager."""
        self._hass = hass
        self._address = address
        self._client: BleakClient | None = None
        self._lock = asyncio.Lock()
        self._disconnect_handle: asyncio.TimerHandle | None = None
        self._loop: asyncio.AbstractEventLoop = asyncio.get_event_loop()

    async def write_brightness(self, value: int) -> bool:
        """Write brightness value (0-100) to the device.

        Returns True on success, False on failure.
        """
        for attempt in range(MAX_RETRIES):
            try:
                async with self._lock:
                    self._cancel_disconnect()
                    await self._ensure_connected()
                    if self._client is None or not self._client.is_connected:
                        raise BleakError("Connection failed")
                    _LOGGER.debug(
                        "Writing brightness %d (0x%02X) to %s (attempt %d)",
                        value,
                        value,
                        self._address,
                        attempt + 1,
                    )
                    
                    # Some BLE devices require reading before writing
                    # Read current value first
                    try:
                        current = await self._client.read_gatt_char(BRIGHTNESS_CHAR_UUID)
                        _LOGGER.debug("Current brightness before write: %d (0x%02X)", current[0], current[0])
                    except BleakError as e:
                        _LOGGER.debug("Pre-write read failed (continuing anyway): %s", e)
                    
                    # Send as single byte (0x00-0x64 for 0-100%)
                    data = bytes([value])
                    _LOGGER.debug("Sending %d bytes: %s (hex: %s) to %s", 
                                  len(data), list(data), data.hex(), BRIGHTNESS_CHAR_UUID)
                    
                    await self._client.write_gatt_char(
                        BRIGHTNESS_CHAR_UUID, data, response=True
                    )
                    _LOGGER.debug("Write completed successfully")
                    
                    # Read back to confirm
                    try:
                        after = await self._client.read_gatt_char(BRIGHTNESS_CHAR_UUID)
                        _LOGGER.debug("Brightness after write: %d (0x%02X)", after[0], after[0])
                    except BleakError as e:
                        _LOGGER.debug("Post-write read failed: %s", e)
                    self._schedule_disconnect()
                    return True
            except (BleakError, TimeoutError, OSError, ValueError) as err:
                _LOGGER.warning(
                    "BLE write failed for %s (attempt %d/%d): %s",
                    self._address,
                    attempt + 1,
                    MAX_RETRIES,
                    err,
                )
                # Force reconnect on next attempt
                await self._force_disconnect()
                if attempt + 1 >= MAX_RETRIES:
                    _LOGGER.error(
                        "BLE write failed for %s after %d attempts",
                        self._address,
                        MAX_RETRIES,
                    )
                    return False
        return False

    async def read_brightness(self) -> int | None:
        """Read current brightness from the device.

        Returns brightness value (0-100) or None on failure.
        """
        for attempt in range(MAX_RETRIES):
            try:
                async with self._lock:
                    self._cancel_disconnect()
                    await self._ensure_connected()
                    if self._client is None or not self._client.is_connected:
                        raise BleakError("Connection failed")
                    data = await self._client.read_gatt_char(BRIGHTNESS_CHAR_UUID)
                    self._schedule_disconnect()
                    value = data[0]
                    _LOGGER.debug(
                        "Read brightness %d (0x%02X) from %s",
                        value,
                        value,
                        self._address,
                    )
                    return value
            except (BleakError, TimeoutError, OSError, ValueError) as err:
                _LOGGER.warning(
                    "BLE read failed for %s (attempt %d/%d): %s",
                    self._address,
                    attempt + 1,
                    MAX_RETRIES,
                    err,
                )
                await self._force_disconnect()
                if attempt + 1 >= MAX_RETRIES:
                    _LOGGER.error(
                        "BLE read failed for %s after %d attempts",
                        self._address,
                        MAX_RETRIES,
                    )
                    return None
        return None

    async def _ensure_connected(self) -> None:
        """Ensure we have an active BLE connection with proper bonding."""
        if self._client is not None and self._client.is_connected:
            return

        # Get BLE device from HA's bluetooth manager
        ble_device = bluetooth.async_ble_device_from_address(
            self._hass, self._address, connectable=True
        )
        if ble_device is None:
            ble_device = bluetooth.async_ble_device_from_address(
                self._hass, self._address, connectable=False
            )
        if ble_device is None:
            raise BleakDeviceNotFoundError(
                f"Flos String Light {self._address} not found by bluetooth adapter"
            )

        _LOGGER.debug("Connecting to Flos String Light %s using bleak-retry-connector", self._address)
        
        # Use HA's recommended connection method
        self._client = await establish_connection(
            BleakClientWithServiceCache,
            ble_device,
            self._address,
            disconnected_callback=self._on_disconnected,
            max_attempts=3,
        )
        
        _LOGGER.info("Connected to Flos String Light %s", self._address)
        
        # Give the device time to stabilize after connection
        await asyncio.sleep(0.5)
        
        # Ensure services are discovered
        if self._client.services:
            char = self._client.services.get_characteristic(BRIGHTNESS_CHAR_UUID)
            if char:
                _LOGGER.debug("Found brightness characteristic: %s, properties: %s", char.uuid, char.properties)
                
                # Read descriptors - some devices need this before accepting writes
                for descriptor in char.descriptors:
                    try:
                        desc_value = await self._client.read_gatt_descriptor(descriptor.handle)
                        _LOGGER.debug("Descriptor %s (handle %d): %s", 
                                      descriptor.uuid, descriptor.handle, desc_value.hex())
                    except (BleakError, ValueError) as e:
                        _LOGGER.debug("Could not read descriptor %s: %s", descriptor.uuid, e)
                
                # Enable notifications/indications on the characteristic.
                # Bleak (HA 2026.10+) refuses direct writes to the CCCD (0x2902)
                # and raises ValueError; start_notify() writes the CCCD itself
                # (indications when the characteristic only supports indicate).
                if "notify" in char.properties or "indicate" in char.properties:
                    try:
                        await self._client.start_notify(char, self._on_notification)
                        _LOGGER.debug(
                            "Subscribed to %s on %s (properties: %s)",
                            char.uuid,
                            self._address,
                            char.properties,
                        )
                    except (BleakError, ValueError) as e:
                        _LOGGER.debug("Could not subscribe to %s: %s", char.uuid, e)
                
                # Wait for device to be fully ready after descriptor operations
                await asyncio.sleep(1.0)
                _LOGGER.debug("Device ready for writes")
            else:
                _LOGGER.warning("Brightness characteristic %s not found in services", BRIGHTNESS_CHAR_UUID)

    def _on_notification(self, _char: Any, data: bytearray) -> None:
        """Log notifications/indications from the brightness characteristic."""
        _LOGGER.debug("Notification from %s: %s", self._address, bytes(data).hex())

    def _on_disconnected(self, client: BleakClient) -> None:
        """Handle unexpected disconnection."""
        _LOGGER.debug("Flos String Light %s disconnected", self._address)
        self._client = None
        self._cancel_disconnect()

    def _schedule_disconnect(self) -> None:
        """Schedule a delayed disconnect."""
        self._disconnect_handle = self._loop.call_later(
            DISCONNECT_DELAY,
            lambda: asyncio.ensure_future(self._do_disconnect()),
        )

    def _cancel_disconnect(self) -> None:
        """Cancel a pending delayed disconnect."""
        if self._disconnect_handle is not None:
            self._disconnect_handle.cancel()
            self._disconnect_handle = None

    async def _do_disconnect(self) -> None:
        """Perform the delayed disconnect."""
        self._disconnect_handle = None
        if self._client is not None and self._client.is_connected:
            _LOGGER.debug(
                "Delayed disconnect from Flos String Light %s", self._address
            )
            try:
                await self._client.disconnect()
            except BleakError as err:
                _LOGGER.debug("Error during disconnect: %s", err)
            self._client = None

    async def _force_disconnect(self) -> None:
        """Force disconnect and reset client state."""
        self._cancel_disconnect()
        if self._client is not None:
            try:
                if self._client.is_connected:
                    await self._client.disconnect()
            except (BleakError, OSError):
                pass
            self._client = None

    async def disconnect(self) -> None:
        """Clean disconnect — called on unload."""
        self._cancel_disconnect()
        await self._force_disconnect()


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Flos String Light from a config entry."""
    address = entry.data[CONF_ADDRESS]
    name = entry.data.get(CONF_NAME, f"Flos String {address[-8:]}")

    manager = FlosStringBLEManager(hass, address)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = manager

    async_add_entities([FlosStringLight(manager, entry, name, address)])


class FlosStringLight(LightEntity):
    """Representation of a Flos String Light."""

    _attr_has_entity_name = True
    _attr_color_mode = ColorMode.BRIGHTNESS
    _attr_supported_color_modes = {ColorMode.BRIGHTNESS}
    _attr_should_poll = True

    def __init__(
        self,
        manager: FlosStringBLEManager,
        entry: ConfigEntry,
        name: str,
        address: str,
    ) -> None:
        """Initialize the light."""
        self._manager = manager
        self._address = address

        # Entity attributes
        self._attr_unique_id = address.upper().replace(":", "")
        self._attr_name = None  # Uses device name
        self._attr_brightness: int | None = None
        self._attr_is_on: bool | None = None
        self._attr_available = False

        # Device info for HA device registry
        self._attr_device_info = {
            "identifiers": {(DOMAIN, address.upper())},
            "name": name,
            "manufacturer": "Flos",
            "model": "String Light",
        }

        # Track last non-zero brightness for turn_on without brightness arg
        self._last_brightness_pct: int = DEFAULT_BRIGHTNESS_PCT

        # Start available so controls are visible even before first read
        self._attr_available = True
        self._attr_is_on = None

        _LOGGER.debug("Initialized FlosStringLight: %s (%s)", name, address)

    async def async_added_to_hass(self) -> None:
        """Run when entity is added to HA."""
        # Try to read the current state from the device
        await self._async_read_state()

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the light on."""
        if ATTR_BRIGHTNESS in kwargs:
            flos_pct = ha_to_flos(kwargs[ATTR_BRIGHTNESS])
        else:
            flos_pct = self._last_brightness_pct

        success = await self._manager.write_brightness(flos_pct)

        if success:
            # Optimistic update
            self._attr_is_on = True
            self._attr_brightness = flos_to_ha(flos_pct)
            self._last_brightness_pct = flos_pct
            self._attr_available = True
            self.async_write_ha_state()
        else:
            _LOGGER.error("Failed to turn on Flos String Light %s", self._address)
            self._attr_available = False
            self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the light off."""
        success = await self._manager.write_brightness(0)

        if success:
            # Optimistic update
            self._attr_is_on = False
            self._attr_brightness = 0
            self._attr_available = True
            self.async_write_ha_state()
        else:
            _LOGGER.error("Failed to turn off Flos String Light %s", self._address)
            self._attr_available = False
            self.async_write_ha_state()

    async def async_update(self) -> None:
        """Poll the device for current state."""
        await self._async_read_state()

    async def _async_read_state(self) -> None:
        """Read brightness from the device and update state."""
        # Check if the device is visible to any BT adapter (connectable or not)
        present = bluetooth.async_address_present(
            self.hass, self._address, connectable=False
        )
        if not present:
            if self._attr_available:
                _LOGGER.debug(
                    "Flos String Light %s not present in bluetooth", self._address
                )
            # Don't mark unavailable immediately — keep controls visible
            return

        flos_pct = await self._manager.read_brightness()

        if flos_pct is not None:
            self._attr_available = True
            if flos_pct == 0:
                self._attr_is_on = False
                self._attr_brightness = 0
            else:
                self._attr_is_on = True
                self._attr_brightness = flos_to_ha(flos_pct)
                self._last_brightness_pct = flos_pct
        else:
            # Read failed — don't flip available immediately if we had
            # a successful optimistic write recently; just keep previous state.
            # Only mark unavailable if we also can't see the device.
            if not present:
                self._attr_available = False

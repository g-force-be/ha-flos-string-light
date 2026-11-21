"""Base entity for Flos String Light."""

from __future__ import annotations

from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import callback
from homeassistant.helpers.device_registry import CONNECTION_BLUETOOTH
from homeassistant.helpers.entity import Entity

from . import FlosStringConfigEntry
from .ble import FlosStringBLEManager
from .const import DOMAIN
from .util import clean_name


class FlosStringEntity(Entity):
    """An entity of one lamp.

    The state comes from the manager, which keeps the connection open and passes
    on what the lamp reports; nothing is polled here.
    """

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(
        self, manager: FlosStringBLEManager, entry: FlosStringConfigEntry
    ) -> None:
        """Initialize the entity."""
        address: str = entry.data[CONF_ADDRESS]
        self._manager = manager
        self._attr_unique_id = address.upper().replace(":", "")
        self._attr_device_info = {
            "identifiers": {(DOMAIN, address.upper())},
            # Shown on the device page as the lamp's Bluetooth address.
            "connections": {(CONNECTION_BLUETOOTH, address.upper())},
            # Entries made before the names were cleaned still hold the lamp's
            # NUL padding.
            "name": clean_name(entry.data.get(CONF_NAME))
            or f"Flos String {address[-8:]}",
            "manufacturer": "Flos",
            "model": "String Light",
        }

    async def async_added_to_hass(self) -> None:
        """Follow the manager from now on."""
        self.async_on_remove(self._manager.async_add_listener(self._handle_update))

    @callback
    def _handle_update(self) -> None:
        """The lamp's state or the connection changed."""
        self.async_write_ha_state()

    @property
    def available(self) -> bool:
        """Available means connected."""
        return self._manager.available

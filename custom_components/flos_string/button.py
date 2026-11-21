"""Button platform for Flos String Light: reconnect to the lamp."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import FlosStringConfigEntry
from .ble import FlosStringBLEManager
from .entity import FlosStringEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FlosStringConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the reconnect button from a config entry."""
    async_add_entities([FlosStringReconnect(entry.runtime_data, entry)])


class FlosStringReconnect(FlosStringEntity, ButtonEntity):
    """Close the connection to the lamp and open a new one.

    For a lamp that is connected but does not do what it is told.
    """

    _attr_translation_key = "reconnect"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self, manager: FlosStringBLEManager, entry: FlosStringConfigEntry
    ) -> None:
        """Initialize the reconnect button."""
        super().__init__(manager, entry)
        self._attr_unique_id = f"{self._attr_unique_id}_reconnect"

    async def async_press(self) -> None:
        """Reconnect to the lamp."""
        await self._manager.async_reconnect()

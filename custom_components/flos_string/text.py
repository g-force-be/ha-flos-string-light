"""Text platform for Flos String Light: the lamp's own name."""

from __future__ import annotations

from homeassistant.components.text import TextEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import FlosStringConfigEntry
from .ble import FlosStringBLEManager
from .const import NAME_LENGTH
from .entity import FlosStringEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FlosStringConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the name entity from a config entry."""
    async_add_entities([FlosStringName(entry.runtime_data, entry)])


class FlosStringName(FlosStringEntity, TextEntity):
    """The name stored in the lamp, as it advertises it over Bluetooth.

    Changing it does not rename the device or its entities in Home Assistant.
    """

    _attr_translation_key = "name"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_native_min = 1
    # Characters; the manager counts the bytes, which is what the lamp limits.
    _attr_native_max = NAME_LENGTH

    def __init__(
        self, manager: FlosStringBLEManager, entry: FlosStringConfigEntry
    ) -> None:
        """Initialize the name entity."""
        super().__init__(manager, entry)
        self._attr_unique_id = f"{self._attr_unique_id}_name"

    @property
    def native_value(self) -> str | None:
        """Return the lamp's name, without its NUL padding."""
        return self._manager.name

    async def async_set_value(self, value: str) -> None:
        """Write a new name to the lamp."""
        await self._manager.async_set_name(value)

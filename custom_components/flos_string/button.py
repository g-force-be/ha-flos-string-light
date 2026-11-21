"""Button platform for Flos String Light: reconnect to the lamp, or refresh it."""

from __future__ import annotations

from homeassistant.components.button import DOMAIN as BUTTON_DOMAIN, ButtonEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import FlosStringConfigEntry
from .ble import FlosStringBLEManager
from .const import DOMAIN
from .entity import FlosStringEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FlosStringConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the button that goes with the way the lamp is connected."""
    manager = entry.runtime_data
    button: FlosStringButton = (
        FlosStringRefresh(manager, entry)
        if manager.on_demand
        else FlosStringReconnect(manager, entry)
    )
    # The other button belongs to the other way of connecting: take it away.
    registry = er.async_get(hass)
    for other in (FlosStringReconnect, FlosStringRefresh):
        if isinstance(button, other):
            continue
        if entity_id := registry.async_get_entity_id(
            BUTTON_DOMAIN, DOMAIN, other(manager, entry).unique_id
        ):
            registry.async_remove(entity_id)
    async_add_entities([button])


class FlosStringButton(FlosStringEntity, ButtonEntity):
    """A button of one lamp, under Configuration on the device page."""

    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self, manager: FlosStringBLEManager, entry: FlosStringConfigEntry
    ) -> None:
        """Initialize the button."""
        super().__init__(manager, entry)
        self._attr_unique_id = f"{self._attr_unique_id}_{self._attr_translation_key}"


class FlosStringReconnect(FlosStringButton):
    """Close the connection to the lamp and open a new one.

    For a lamp that stays connected but does not do what it is told.
    """

    _attr_translation_key = "reconnect"

    async def async_press(self) -> None:
        """Reconnect to the lamp."""
        await self._manager.async_reconnect()


class FlosStringRefresh(FlosStringButton):
    """Connect to the lamp, read its state and disconnect.

    For a lamp that is connected on demand: read it now, not at the next poll.
    """

    _attr_translation_key = "refresh"

    @property
    def available(self) -> bool:
        """Always: it is also the way to try a lamp that could not be reached."""
        return True

    async def async_press(self) -> None:
        """Read the lamp's state."""
        await self._manager.async_refresh()

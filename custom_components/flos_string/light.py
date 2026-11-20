"""Light platform for Flos String Light."""

from __future__ import annotations

from typing import Any

from homeassistant.components.light import ATTR_BRIGHTNESS, ColorMode, LightEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import FlosStringConfigEntry
from .ble import FlosStringBLEManager
from .const import DEFAULT_BRIGHTNESS_PCT
from .entity import FlosStringEntity


def ha_to_flos(ha_brightness: int) -> int:
    """Convert HA brightness (0-255) to Flos brightness (0-100).

    Returns minimum 1 since 0 means OFF on the device.
    """
    return max(1, round(ha_brightness * 100 / 255))


def flos_to_ha(flos_brightness: int) -> int:
    """Convert Flos brightness (0-100) to HA brightness (0-255)."""
    return min(255, round(flos_brightness * 255 / 100))


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FlosStringConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Flos String Light from a config entry."""
    async_add_entities([FlosStringLight(entry.runtime_data, entry)])


class FlosStringLight(FlosStringEntity, LightEntity):
    """Representation of a Flos String Light."""

    _attr_name = None  # Uses device name
    _attr_color_mode = ColorMode.BRIGHTNESS
    _attr_supported_color_modes = {ColorMode.BRIGHTNESS}

    def __init__(
        self, manager: FlosStringBLEManager, entry: FlosStringConfigEntry
    ) -> None:
        """Initialize the light."""
        super().__init__(manager, entry)
        # Last non-zero brightness, for turn_on without a brightness.
        self._last_brightness_pct: int = DEFAULT_BRIGHTNESS_PCT

    async def async_added_to_hass(self) -> None:
        """Follow the manager from now on."""
        await super().async_added_to_hass()
        if self._manager.brightness:
            self._last_brightness_pct = self._manager.brightness

    @callback
    def _handle_update(self) -> None:
        """The brightness or the connection changed."""
        if self._manager.brightness:
            self._last_brightness_pct = self._manager.brightness
        super()._handle_update()

    @property
    def is_on(self) -> bool | None:
        """Return True when the lamp is on; None until the first read."""
        if self._manager.brightness is None:
            return None
        return self._manager.brightness > 0

    @property
    def brightness(self) -> int | None:
        """Return the brightness (0-255)."""
        if self._manager.brightness is None:
            return None
        return flos_to_ha(self._manager.brightness)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the light on, at the given or the last brightness."""
        if ATTR_BRIGHTNESS in kwargs:
            flos_pct = ha_to_flos(kwargs[ATTR_BRIGHTNESS])
        else:
            flos_pct = self._last_brightness_pct
        await self._manager.async_set_brightness(flos_pct)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the light off."""
        await self._manager.async_set_brightness(0)

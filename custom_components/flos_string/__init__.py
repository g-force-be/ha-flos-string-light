"""The Flos String Light integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import HomeAssistant

from .ble import FlosStringBLEManager

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["button", "light", "text"]

type FlosStringConfigEntry = ConfigEntry[FlosStringBLEManager]


async def async_setup_entry(hass: HomeAssistant, entry: FlosStringConfigEntry) -> bool:
    """Set up Flos String Light from a config entry."""
    address = entry.data[CONF_ADDRESS]
    _LOGGER.debug("Setting up Flos String Light: %s", address)

    manager = FlosStringBLEManager(hass, address)
    entry.runtime_data = manager
    # Connects in the background: the setup must not wait for, or fail on, a lamp
    # that is out of reach.
    manager.async_start(entry)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: FlosStringConfigEntry) -> bool:
    """Unload a Flos String Light config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        await entry.runtime_data.async_stop()
    return unload_ok

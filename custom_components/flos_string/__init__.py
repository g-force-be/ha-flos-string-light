"""The Flos String Light integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["light"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Flos String Light from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    _LOGGER.debug(
        "Setting up Flos String Light: %s (%s)",
        entry.title,
        entry.data.get("address"),
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a Flos String Light config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        # Clean up any stored data for this entry
        managers = hass.data.get(DOMAIN, {})
        if entry.entry_id in managers:
            manager = managers.pop(entry.entry_id)
            await manager.disconnect()

    return unload_ok

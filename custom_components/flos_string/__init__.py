"""The Flos String Light integration."""

from __future__ import annotations

import asyncio
import logging
import subprocess

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
import homeassistant.helpers.config_validation as cv

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["light"]

SERVICE_GATTTOOL_WRITE = "gatttool_write"


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Flos String Light from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    _LOGGER.debug(
        "Setting up Flos String Light: %s (%s)",
        entry.title,
        entry.data.get("address"),
    )

    # Register test service (only once)
    if not hass.services.has_service(DOMAIN, SERVICE_GATTTOOL_WRITE):
        async def handle_gatttool_write(call: ServiceCall) -> None:
            """Handle gatttool write service call."""
            address = call.data["address"]
            value = call.data["value"]
            
            _LOGGER.info("gatttool_write: address=%s, value=%s", address, value)
            
            # Convert value to hex string
            hex_value = format(value, '02x')
            
            # Use gatttool to write directly
            # First we need to find the handle - let's try common ones
            # The characteristic UUID 335c1504 typically has handle around 0x0010-0x0015
            
            cmd = f"gatttool -b {address} --char-write-req --handle=0x0011 --value={hex_value}"
            _LOGGER.info("Running: %s", cmd)
            
            try:
                result = await asyncio.to_thread(
                    subprocess.run,
                    cmd,
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                _LOGGER.info("gatttool stdout: %s", result.stdout)
                _LOGGER.info("gatttool stderr: %s", result.stderr)
                _LOGGER.info("gatttool returncode: %s", result.returncode)
            except subprocess.TimeoutExpired:
                _LOGGER.error("gatttool timed out")
            except Exception as e:
                _LOGGER.error("gatttool error: %s", e)

        hass.services.async_register(
            DOMAIN,
            SERVICE_GATTTOOL_WRITE,
            handle_gatttool_write,
            schema=vol.Schema({
                vol.Required("address"): cv.string,
                vol.Required("value"): vol.All(vol.Coerce(int), vol.Range(min=0, max=100)),
            }),
        )
        _LOGGER.info("Registered service: %s.%s", DOMAIN, SERVICE_GATTTOOL_WRITE)

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

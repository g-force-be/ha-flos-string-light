"""The Flos String Light integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import HomeAssistant

from .ble import FlosStringBLEManager
from .const import (
    CONF_CONNECT_ATTEMPTS,
    CONF_HOLD_TIME,
    CONF_CONNECTION,
    CONF_POLL_INTERVAL,
    CONF_POWER_CHECK_INTERVAL,
    CONF_RETRY_INTERVAL,
    CONF_TAKE_TURNS,
    CONF_VISIT_LIMIT,
    CONF_VISIT_WINDOW,
    CONNECTION_ALWAYS,
    CONNECTION_ON_DEMAND,
    DEFAULT_CONNECT_ATTEMPTS,
    DEFAULT_HOLD_TIME,
    DEFAULT_POLL_INTERVAL,
    DEFAULT_POWER_CHECK_INTERVAL,
    DEFAULT_RETRY_INTERVAL,
    DEFAULT_TAKE_TURNS,
    DEFAULT_VISIT_LIMIT,
    DEFAULT_VISIT_WINDOW,
)
from .util import second_connection

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["button", "light", "sensor", "text"]

type FlosStringConfigEntry = ConfigEntry[FlosStringBLEManager]


async def async_setup_entry(hass: HomeAssistant, entry: FlosStringConfigEntry) -> bool:
    """Set up Flos String Light from a config entry."""
    address = entry.data[CONF_ADDRESS]
    _LOGGER.debug("Setting up Flos String Light: %s", address)

    options = entry.options
    manager = FlosStringBLEManager(
        hass,
        address,
        on_demand=options.get(CONF_CONNECTION, CONNECTION_ALWAYS)
        == CONNECTION_ON_DEMAND,
        # Minutes in the options, seconds in the manager.
        poll_interval=options.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL) * 60,
        power_check_interval=options.get(
            CONF_POWER_CHECK_INTERVAL, DEFAULT_POWER_CHECK_INTERVAL
        ),
        hold_time=options.get(CONF_HOLD_TIME, DEFAULT_HOLD_TIME),
        visit_limit=options.get(CONF_VISIT_LIMIT, DEFAULT_VISIT_LIMIT),
        visit_window=options.get(CONF_VISIT_WINDOW, DEFAULT_VISIT_WINDOW),
        take_turns=options.get(CONF_TAKE_TURNS, DEFAULT_TAKE_TURNS),
        second_connection=second_connection(options),
        connect_attempts=options.get(
            CONF_CONNECT_ATTEMPTS, DEFAULT_CONNECT_ATTEMPTS
        ),
        retry_interval=options.get(CONF_RETRY_INTERVAL, DEFAULT_RETRY_INTERVAL),
    )
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

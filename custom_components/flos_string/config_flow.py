"""Config flow for Flos String Light integration."""

from __future__ import annotations

import logging
import re
from typing import Any

import voluptuous as vol

from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_discovered_service_info,
)
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_ADDRESS, CONF_NAME

from .const import DOMAIN, SERVICE_UUID

_LOGGER = logging.getLogger(__name__)

MAC_REGEX = re.compile(r"^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$")


class FlosStringConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Flos String Light."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._discovery_info: BluetoothServiceInfoBleak | None = None

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> ConfigFlowResult:
        """Handle bluetooth discovery."""
        _LOGGER.debug(
            "Discovered Flos String Light: %s (%s)",
            discovery_info.name,
            discovery_info.address,
        )

        await self.async_set_unique_id(discovery_info.address.upper())
        self._abort_if_unique_id_configured()

        self._discovery_info = discovery_info
        name = discovery_info.name or f"Flos String {discovery_info.address[-8:]}"

        self.context["title_placeholders"] = {"name": name}

        return await self.async_step_bluetooth_confirm()

    async def async_step_bluetooth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm discovery of a Flos String Light."""
        assert self._discovery_info is not None

        if user_input is not None:
            name = user_input.get(
                CONF_NAME,
                self._discovery_info.name
                or f"Flos String {self._discovery_info.address[-8:]}",
            )
            return self.async_create_entry(
                title=name,
                data={
                    CONF_ADDRESS: self._discovery_info.address.upper(),
                    CONF_NAME: name,
                },
            )

        name = self._discovery_info.name or f"Flos String {self._discovery_info.address[-8:]}"

        return self.async_show_form(
            step_id="bluetooth_confirm",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_NAME, default=name): str,
                }
            ),
            description_placeholders={"name": name},
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle manual configuration."""
        errors: dict[str, str] = {}

        if user_input is not None:
            address = user_input[CONF_ADDRESS].strip().upper()

            # Validate MAC address format
            if not MAC_REGEX.match(address):
                errors[CONF_ADDRESS] = "invalid_mac"
            else:
                await self.async_set_unique_id(address)
                self._abort_if_unique_id_configured()

                name = user_input.get(CONF_NAME, f"Flos String {address[-8:]}")

                return self.async_create_entry(
                    title=name,
                    data={
                        CONF_ADDRESS: address,
                        CONF_NAME: name,
                    },
                )

        # Check for any already-discovered Flos devices to show as hint
        discovered: list[str] = []
        for info in async_discovered_service_info(self.hass, connectable=True):
            if SERVICE_UUID in [str(u).lower() for u in info.service_uuids]:
                discovered.append(f"{info.name or 'Unknown'} ({info.address})")

        description_placeholders = {}
        if discovered:
            description_placeholders["discovered"] = ", ".join(discovered)

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_ADDRESS): str,
                    vol.Optional(CONF_NAME, default="Flos String Light"): str,
                }
            ),
            errors=errors,
            description_placeholders=description_placeholders,
        )

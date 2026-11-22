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
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    BooleanSelector,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .const import (
    CONF_CONNECT_ATTEMPTS,
    CONF_CONNECT_TWICE,
    CONF_CONNECTION,
    CONF_POLL_INTERVAL,
    CONF_POWER_CHECK_INTERVAL,
    CONF_RETRY_INTERVAL,
    CONF_VISIT_LIMIT,
    CONF_VISIT_WINDOW,
    CONNECTION_ALWAYS,
    CONNECTION_ON_DEMAND,
    DEFAULT_CONNECT_ATTEMPTS,
    DEFAULT_CONNECT_TWICE,
    DEFAULT_POLL_INTERVAL,
    DEFAULT_POWER_CHECK_INTERVAL,
    DEFAULT_RETRY_INTERVAL,
    DEFAULT_VISIT_LIMIT,
    DEFAULT_VISIT_WINDOW,
    DOMAIN,
    SERVICE_UUID,
)
from .util import clean_name

_LOGGER = logging.getLogger(__name__)

MAC_REGEX = re.compile(r"^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$")


def _whole_number(low: int, high: int, unit: str | None = None) -> vol.All:
    """A whole number between low and high, typed in a box."""
    config = NumberSelectorConfig(
        min=low, max=high, step=1, mode=NumberSelectorMode.BOX
    )
    if unit is not None:
        config["unit_of_measurement"] = unit
    return vol.All(NumberSelector(config), vol.Coerce(int))


OPTIONS_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_CONNECTION, default=CONNECTION_ALWAYS): SelectSelector(
            SelectSelectorConfig(
                options=[CONNECTION_ALWAYS, CONNECTION_ON_DEMAND],
                translation_key=CONF_CONNECTION,
                mode=SelectSelectorMode.LIST,
            )
        ),
        vol.Required(
            CONF_POLL_INTERVAL, default=DEFAULT_POLL_INTERVAL
        ): _whole_number(0, 1440, "min"),
        vol.Required(
            CONF_POWER_CHECK_INTERVAL, default=DEFAULT_POWER_CHECK_INTERVAL
        ): _whole_number(0, 3600, "s"),
        vol.Required(
            CONF_VISIT_LIMIT, default=DEFAULT_VISIT_LIMIT
        ): _whole_number(0, 100),
        vol.Required(
            CONF_VISIT_WINDOW, default=DEFAULT_VISIT_WINDOW
        ): _whole_number(1, 3600, "s"),
        vol.Required(
            CONF_CONNECT_TWICE, default=DEFAULT_CONNECT_TWICE
        ): BooleanSelector(),
        vol.Required(
            CONF_CONNECT_ATTEMPTS, default=DEFAULT_CONNECT_ATTEMPTS
        ): _whole_number(1, 5),
        vol.Required(
            CONF_RETRY_INTERVAL, default=DEFAULT_RETRY_INTERVAL
        ): _whole_number(1, 600, "s"),
    }
)


class FlosStringConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Flos String Light."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._discovery_info: BluetoothServiceInfoBleak | None = None

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> FlosStringOptionsFlow:
        """Return the options flow of a lamp."""
        return FlosStringOptionsFlow()

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> ConfigFlowResult:
        """Handle bluetooth discovery."""
        _LOGGER.debug(
            "Discovered Flos String Light: %s (%s)",
            clean_name(discovery_info.name),
            discovery_info.address,
        )

        await self.async_set_unique_id(discovery_info.address.upper())
        self._abort_if_unique_id_configured()

        self._discovery_info = discovery_info

        self.context["title_placeholders"] = {"name": self._discovered_name()}

        return await self.async_step_bluetooth_confirm()

    def _discovered_name(self) -> str:
        """Name of the discovered lamp, without the NULs it pads its name with."""
        assert self._discovery_info is not None
        return (
            clean_name(self._discovery_info.name)
            or f"Flos String {self._discovery_info.address[-8:]}"
        )

    async def async_step_bluetooth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm discovery of a Flos String Light."""
        assert self._discovery_info is not None

        name = self._discovered_name()

        if user_input is not None:
            name = clean_name(user_input.get(CONF_NAME)) or name
            return self.async_create_entry(
                title=name,
                data={
                    CONF_ADDRESS: self._discovery_info.address.upper(),
                    CONF_NAME: name,
                },
            )

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

                name = (
                    clean_name(user_input.get(CONF_NAME))
                    or f"Flos String {address[-8:]}"
                )

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
                discovered.append(
                    f"{clean_name(info.name) or 'Unknown'} ({info.address})"
                )

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


class FlosStringOptionsFlow(OptionsFlowWithReload):
    """How Home Assistant connects to a lamp; saving reloads the lamp's entry."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Choose between staying connected and connecting on demand."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                OPTIONS_SCHEMA, self.config_entry.options
            ),
        )

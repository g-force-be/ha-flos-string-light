"""The switch that gives a lamp its power: another entity of Home Assistant.

A relay in front of the lamp, for one. It is an option of the lamp, and the lamp
works without it. The switch is followed through its state and told what to do
through Home Assistant's own services; nothing here talks to the relay itself.
"""

from __future__ import annotations

from collections.abc import Callable

from homeassistant.const import (
    ATTR_ENTITY_ID,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
    STATE_OFF,
    STATE_ON,
)
from homeassistant.core import (
    CALLBACK_TYPE,
    DOMAIN as HOMEASSISTANT_DOMAIN,
    Event,
    EventStateChangedData,
    HomeAssistant,
    State,
    callback,
)
from homeassistant.helpers.event import async_track_state_change_event


def _is_on(state: State | None) -> bool | None:
    """Return whether a state says on or off; None when it says neither."""
    if state is None:
        return None
    if state.state == STATE_ON:
        return True
    if state.state == STATE_OFF:
        return False
    return None


class PowerSwitch:
    """The entity that switches the power of one lamp."""

    def __init__(self, hass: HomeAssistant, entity_id: str) -> None:
        """Follow entity_id; it need not exist yet."""
        self._hass = hass
        self.entity_id = entity_id

    @property
    def is_on(self) -> bool | None:
        """Return whether the lamp has power.

        None when the switch cannot be used: it does not exist, or it is
        unavailable or unknown. The lamp then goes without a switch.
        """
        return _is_on(self._hass.states.get(self.entity_id))

    async def async_turn_on(self) -> None:
        """Give the lamp its power."""
        await self._call(SERVICE_TURN_ON)

    async def async_turn_off(self) -> None:
        """Cut the lamp's power."""
        await self._call(SERVICE_TURN_OFF)

    async def _call(self, service: str) -> None:
        await self._hass.services.async_call(
            HOMEASSISTANT_DOMAIN,
            service,
            {ATTR_ENTITY_ID: self.entity_id},
            blocking=True,
        )

    @callback
    def async_listen(self, listener: Callable[[], None]) -> CALLBACK_TYPE:
        """Call listener whenever is_on changes; return how to stop that."""

        @callback
        def changed(event: Event[EventStateChangedData]) -> None:
            if _is_on(event.data["old_state"]) != _is_on(event.data["new_state"]):
                listener()

        return async_track_state_change_event(self._hass, [self.entity_id], changed)

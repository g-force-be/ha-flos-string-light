"""Sensor platform for Flos String Light: how well Home Assistant hears the lamp."""

from __future__ import annotations

from homeassistant.components.sensor import (
    DOMAIN as SENSOR_DOMAIN,
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import SIGNAL_STRENGTH_DECIBELS_MILLIWATT, EntityCategory
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
    """Set up the sensors of a lamp that is connected on demand."""
    manager = entry.runtime_data
    sensors = [FlosStringSignal(manager, entry), FlosStringProxy(manager, entry)]
    if manager.on_demand:
        async_add_entities(sensors)
        return
    # A lamp that stays connected does not advertise: there is nothing to show.
    registry = er.async_get(hass)
    for sensor in sensors:
        if entity_id := registry.async_get_entity_id(
            SENSOR_DOMAIN, DOMAIN, sensor.unique_id
        ):
            registry.async_remove(entity_id)


class FlosStringSensor(FlosStringEntity, SensorEntity):
    """A sensor of one lamp, under Diagnostic on the device page.

    It shows the signal of a lamp that advertises, also when connecting to it
    fails: that is when the signal matters most.
    """

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _key: str

    def __init__(
        self, manager: FlosStringBLEManager, entry: FlosStringConfigEntry
    ) -> None:
        """Initialize the sensor."""
        super().__init__(manager, entry)
        self._attr_unique_id = f"{self._attr_unique_id}_{self._key}"

    @property
    def available(self) -> bool:
        """Available while a proxy hears the lamp, also when it cannot be reached."""
        return self._manager.rssi is not None


class FlosStringSignal(FlosStringSensor):
    """The lamp's signal at the Bluetooth proxy that hears it best."""

    _key = "signal_strength"
    _attr_device_class = SensorDeviceClass.SIGNAL_STRENGTH
    _attr_native_unit_of_measurement = SIGNAL_STRENGTH_DECIBELS_MILLIWATT
    _attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self) -> int | None:
        """Return the signal strength in dBm."""
        return self._manager.rssi


class FlosStringProxy(FlosStringSensor):
    """The Bluetooth adapter or proxy that hears the lamp best."""

    _key = "proxy"
    _attr_translation_key = "proxy"

    @property
    def native_value(self) -> str | None:
        """Return the name of the adapter or proxy."""
        return self._manager.proxy

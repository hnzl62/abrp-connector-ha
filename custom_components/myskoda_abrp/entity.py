"""Shared base entity for the ABRP telemetry service device."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity

from .const import CONF_VEHICLE_DEVICE_ID, DOMAIN, MANUFACTURER, MYSKODA_DOMAIN
from .telemetry import TelemetrySender


def build_device_info(hass: HomeAssistant, entry: ConfigEntry) -> DeviceInfo:
    """Build DeviceInfo for our own service device, linked to the MySkoda vehicle."""
    via_device: tuple[str, str] | None = None
    vehicle_device_id = entry.data.get(CONF_VEHICLE_DEVICE_ID)
    if vehicle_device_id:
        vehicle_device = dr.async_get(hass).async_get(vehicle_device_id)
        if vehicle_device is not None:
            vin = next(
                (ident[1] for ident in vehicle_device.identifiers if ident[0] == MYSKODA_DOMAIN),
                None,
            )
            if vin is not None:
                via_device = (MYSKODA_DOMAIN, vin)

    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name=f"{entry.title} ABRP Telemetry",
        manufacturer=MANUFACTURER,
        model="ABRP Telemetry Bridge",
        via_device=via_device,
    )


class MySkodaAbrpEntity(Entity):
    """Base class for entities belonging to one config entry's service device."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, sender: TelemetrySender, entry: ConfigEntry, key: str) -> None:
        self._sender = sender
        self._entry_id = entry.entry_id
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_device_info = build_device_info(sender.hass, entry)

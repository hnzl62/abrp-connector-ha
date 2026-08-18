"""Diagnostic sensors for MySkoda → ABRP Telemetry."""
from __future__ import annotations

import json

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import ATTR_LAST_PAYLOAD, DOMAIN, signal_update
from .entity import MySkodaAbrpEntity
from .telemetry import TelemetrySender


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    sender: TelemetrySender = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            LastSuccessfulSendSensor(sender, entry),
            LastErrorSensor(sender, entry),
        ]
    )


class LastSuccessfulSendSensor(MySkodaAbrpEntity, SensorEntity):
    """Timestamp of the last telemetry payload ABRP accepted."""

    _attr_translation_key = "last_successful_send"
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, sender: TelemetrySender, entry: ConfigEntry) -> None:
        super().__init__(sender, entry, "last_successful_send")

    @property
    def native_value(self):
        return self._sender.last_success_at

    @property
    def extra_state_attributes(self) -> dict[str, str] | None:
        if self._sender.last_payload is None:
            return None
        return {ATTR_LAST_PAYLOAD: json.dumps(self._sender.last_payload)}

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, signal_update(self._entry_id), self._handle_update
            )
        )

    @callback
    def _handle_update(self) -> None:
        self.async_write_ha_state()


class LastErrorSensor(MySkodaAbrpEntity, SensorEntity):
    """Most recent error message from a failed telemetry send, if any."""

    _attr_translation_key = "last_error"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, sender: TelemetrySender, entry: ConfigEntry) -> None:
        super().__init__(sender, entry, "last_error")

    @property
    def native_value(self) -> str:
        return self._sender.last_error or "ok"

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, signal_update(self._entry_id), self._handle_update
            )
        )

    @callback
    def _handle_update(self) -> None:
        self.async_write_ha_state()

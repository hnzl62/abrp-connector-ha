"""Switch to pause/resume ABRP telemetry sending without removing the integration."""
from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import DOMAIN
from .entity import MySkodaAbrpEntity
from .telemetry import TelemetrySender


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    sender: TelemetrySender = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([TelemetryEnabledSwitch(sender, entry)])


class TelemetryEnabledSwitch(MySkodaAbrpEntity, SwitchEntity, RestoreEntity):
    """Lets the user pause telemetry uploads while keeping the entry configured."""

    _attr_translation_key = "telemetry_enabled"

    def __init__(self, sender: TelemetrySender, entry: ConfigEntry) -> None:
        super().__init__(sender, entry, "telemetry_enabled")

    @property
    def is_on(self) -> bool:
        return self._sender.enabled

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state is not None:
            self._sender.enabled = last_state.state == "on"

    async def async_turn_on(self, **kwargs: Any) -> None:
        self._sender.enabled = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        self._sender.enabled = False
        self.async_write_ha_state()

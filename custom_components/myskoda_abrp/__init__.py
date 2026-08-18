"""The MySkoda → ABRP Telemetry integration."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
    CONF_API_KEY,
    CONF_CAR_MODEL,
    CONF_INTERVAL,
    CONF_ONLY_ON_CHANGE,
    CONF_TIMESTAMP_SOURCE,
    CONF_USER_TOKEN,
    DEFAULT_INTERVAL,
    DEFAULT_ONLY_ON_CHANGE,
    DEFAULT_TIMESTAMP_SOURCE,
    DOMAIN,
    FIELD_SPECS,
    PLATFORMS,
)
from .telemetry import TelemetrySender

_LOGGER = logging.getLogger(__name__)


def _effective_config(entry: ConfigEntry) -> dict[str, Any]:
    """Merge initial setup data with any later options-flow overrides."""
    return {**entry.data, **entry.options}


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    config = _effective_config(entry)

    entity_map = {
        field_key: config[spec.config_key]
        for field_key, spec in FIELD_SPECS.items()
        if spec.config_key in config
    }

    sender = TelemetrySender(
        hass=hass,
        entry=entry,
        api_key=config[CONF_API_KEY],
        user_token=config[CONF_USER_TOKEN],
        car_model=config.get(CONF_CAR_MODEL) or None,
        entity_map=entity_map,
        interval=config.get(CONF_INTERVAL, DEFAULT_INTERVAL),
        timestamp_source=config.get(CONF_TIMESTAMP_SOURCE, DEFAULT_TIMESTAMP_SOURCE),
        only_on_change=config.get(CONF_ONLY_ON_CHANGE, DEFAULT_ONLY_ON_CHANGE),
    )

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = sender
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    sender.async_start()
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        sender: TelemetrySender = hass.data[DOMAIN].pop(entry.entry_id)
        sender.async_stop()
        if not hass.data[DOMAIN]:
            hass.data.pop(DOMAIN)
    return unload_ok


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the entry whenever its options change (interval, credentials, mapping, ...)."""
    await hass.config_entries.async_reload(entry.entry_id)

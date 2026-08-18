"""Config and options flow for MySkoda → ABRP Telemetry.

Flow order deliberately differs from a naive "credentials first" layout:
credentials are collected early (step ``user``) but only cheaply checked for
being non-empty there, since we don't yet know which entity holds the
vehicle's SoC. The live API check happens in the final ``interval`` step,
once the SoC entity is known, so it can validate with a real value and still
fail *during* the flow rather than silently at runtime.
"""
from __future__ import annotations

import logging
from typing import Any, Mapping

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    BooleanSelector,
    EntitySelector,
    EntitySelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)
from homeassistant.util import dt as dt_util

from . import abrp_api
from .const import (
    CONF_API_KEY,
    CONF_CAR_MODEL,
    CONF_INTERVAL,
    CONF_ONLY_ON_CHANGE,
    CONF_TIMESTAMP_SOURCE,
    CONF_USER_TOKEN,
    CONF_VEHICLE_DEVICE_ID,
    DEFAULT_INTERVAL,
    DEFAULT_ONLY_ON_CHANGE,
    DEFAULT_TIMESTAMP_SOURCE,
    DOMAIN,
    FIELD_SOC,
    FIELD_SPECS,
    MAX_INTERVAL,
    MIN_INTERVAL,
    MYSKODA_DOMAIN,
    TIMESTAMP_SOURCE_SEND_TIME,
    TIMESTAMP_SOURCE_VEHICLE,
    FieldSpec,
)

_LOGGER = logging.getLogger(__name__)

UNAVAILABLE_STATES = ("unknown", "unavailable", "")


def _suggest_entity(hass: HomeAssistant, device_id: str, spec: FieldSpec) -> str | None:
    """Best-effort auto-detection of a MySkoda entity for one ABRP field."""
    entity_reg = er.async_get(hass)
    candidates = [
        entry
        for entry in er.async_entries_for_device(
            entity_reg, device_id, include_disabled_entities=False
        )
        if entry.domain == spec.platform.value
    ]
    for suffix in spec.suffixes:
        for entry in candidates:
            object_id = entry.entity_id.split(".", 1)[-1]
            if object_id.endswith(suffix) or (entry.unique_id or "").endswith(suffix):
                return entry.entity_id
    return None


def _current_soc(hass: HomeAssistant, soc_entity_id: str | None) -> float | None:
    if not soc_entity_id:
        return None
    state = hass.states.get(soc_entity_id)
    if state is None or state.state in UNAVAILABLE_STATES:
        return None
    try:
        return float(state.state)
    except ValueError:
        return None


def _entity_field_schema(
    hass: HomeAssistant, device_id: str | None, current: dict[str, Any]
) -> dict[Any, Any]:
    schema_dict: dict[Any, Any] = {}
    for spec in FIELD_SPECS.values():
        default = current.get(spec.config_key)
        if default is None and device_id:
            default = _suggest_entity(hass, device_id, spec)
        selector = EntitySelector(EntitySelectorConfig(domain=spec.platform.value))
        if spec.required:
            marker = (
                vol.Required(spec.config_key, default=default)
                if default
                else vol.Required(spec.config_key)
            )
        else:
            marker = (
                vol.Optional(spec.config_key, default=default)
                if default
                else vol.Optional(spec.config_key)
            )
        schema_dict[marker] = selector
    return schema_dict


class MySkodaAbrpConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the initial setup flow."""

    VERSION = 1

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}
        self._manufacturers: dict[str, dict[str, str]] | None = None
        self._model_fetch_attempted = False
        self._selected_manufacturer: str | None = None
        self._vehicle_name: str | None = None
        self._reauth_entry: ConfigEntry | None = None

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlowHandler:
        return OptionsFlowHandler()

    # -- Step 1: credentials (presence check only; live check happens later) --
    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}
        if user_input is not None:
            api_key = user_input[CONF_API_KEY].strip()
            user_token = user_input[CONF_USER_TOKEN].strip()
            if not api_key:
                errors[CONF_API_KEY] = "required"
            if not user_token:
                errors[CONF_USER_TOKEN] = "required"
            if not errors:
                self._data[CONF_API_KEY] = api_key
                self._data[CONF_USER_TOKEN] = user_token
                return await self.async_step_vehicle()

        schema = vol.Schema(
            {
                vol.Required(CONF_API_KEY): str,
                vol.Required(CONF_USER_TOKEN): str,
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    # -- Step 2: pick the MySkoda vehicle device --
    async def async_step_vehicle(self, user_input: dict[str, Any] | None = None):
        device_reg = dr.async_get(self.hass)
        vehicles = {
            device.id: (device.name_by_user or device.name or device.id)
            for device in device_reg.devices.values()
            if any(ident[0] == MYSKODA_DOMAIN for ident in device.identifiers)
        }

        if not vehicles:
            return self.async_abort(reason="no_myskoda_devices")

        if user_input is not None:
            device_id = user_input[CONF_VEHICLE_DEVICE_ID]
            device = device_reg.async_get(device_id)
            vin = device_id
            if device is not None:
                vin = next(
                    (ident[1] for ident in device.identifiers if ident[0] == MYSKODA_DOMAIN),
                    device_id,
                )
            await self.async_set_unique_id(vin)
            self._abort_if_unique_id_configured()

            self._data[CONF_VEHICLE_DEVICE_ID] = device_id
            self._vehicle_name = vehicles[device_id]
            return await self.async_step_car_model_manufacturer()

        schema = vol.Schema(
            {
                vol.Required(CONF_VEHICLE_DEVICE_ID): SelectSelector(
                    SelectSelectorConfig(
                        options=[
                            SelectOptionDict(label=name, value=dev_id)
                            for dev_id, name in vehicles.items()
                        ],
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                )
            }
        )
        return self.async_show_form(step_id="vehicle", data_schema=schema)

    # -- Step 3a/3b: manufacturer -> model, sourced live from Iternio --
    async def async_step_car_model_manufacturer(self, user_input: dict[str, Any] | None = None):
        if not self._model_fetch_attempted:
            self._model_fetch_attempted = True
            session = async_get_clientsession(self.hass)
            try:
                self._manufacturers = await abrp_api.fetch_car_models(session)
            except abrp_api.AbrpError as err:
                _LOGGER.warning("Could not fetch ABRP car model list: %s", err)
                self._manufacturers = None

        if not self._manufacturers:
            return await self.async_step_car_model_manual()

        if user_input is not None:
            self._selected_manufacturer = user_input["manufacturer"]
            return await self.async_step_car_model()

        manufacturers = sorted(self._manufacturers)
        if "Skoda" in manufacturers:
            manufacturers.insert(0, manufacturers.pop(manufacturers.index("Skoda")))

        schema = vol.Schema(
            {
                vol.Required("manufacturer", default=manufacturers[0]): SelectSelector(
                    SelectSelectorConfig(options=manufacturers, mode=SelectSelectorMode.DROPDOWN)
                )
            }
        )
        return self.async_show_form(step_id="car_model_manufacturer", data_schema=schema)

    async def async_step_car_model(self, user_input: dict[str, Any] | None = None):
        models = (self._manufacturers or {}).get(self._selected_manufacturer or "", {})

        if user_input is not None:
            self._data[CONF_CAR_MODEL] = user_input["model"]
            return await self.async_step_entities()

        options = [
            SelectOptionDict(label=label, value=model_id)
            for label, model_id in sorted(models.items())
        ]
        schema = vol.Schema(
            {
                vol.Required("model"): SelectSelector(
                    SelectSelectorConfig(options=options, mode=SelectSelectorMode.DROPDOWN)
                )
            }
        )
        return self.async_show_form(
            step_id="car_model",
            data_schema=schema,
            description_placeholders={"manufacturer": self._selected_manufacturer or ""},
        )

    async def async_step_car_model_manual(self, user_input: dict[str, Any] | None = None):
        """Fallback when the Iternio car model list could not be fetched."""
        if user_input is not None:
            self._data[CONF_CAR_MODEL] = user_input[CONF_CAR_MODEL].strip()
            return await self.async_step_entities()

        schema = vol.Schema({vol.Optional(CONF_CAR_MODEL, default=""): str})
        return self.async_show_form(step_id="car_model_manual", data_schema=schema)

    # -- Step 4: entity mapping, pre-filled by auto-detection --
    async def async_step_entities(self, user_input: dict[str, Any] | None = None):
        if user_input is not None:
            for key, value in user_input.items():
                if value:
                    self._data[key] = value
                else:
                    self._data.pop(key, None)
            return await self.async_step_interval()

        device_id = self._data.get(CONF_VEHICLE_DEVICE_ID)
        schema = vol.Schema(_entity_field_schema(self.hass, device_id, self._data))
        return self.async_show_form(step_id="entities", data_schema=schema)

    # -- Step 5: send interval + final live credential check --
    async def async_step_interval(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}

        if user_input is not None:
            soc_entity = self._data.get(FIELD_SPECS[FIELD_SOC].config_key)
            soc_value = _current_soc(self.hass, soc_entity)

            if soc_value is not None:
                session = async_get_clientsession(self.hass)
                try:
                    await abrp_api.validate_credentials(
                        session,
                        self._data[CONF_API_KEY],
                        self._data[CONF_USER_TOKEN],
                        soc_value,
                        int(dt_util.utcnow().timestamp()),
                    )
                except abrp_api.AbrpAuthError:
                    errors["base"] = "invalid_auth"
                except abrp_api.AbrpApiError:
                    errors["base"] = "cannot_connect"

            if not errors:
                self._data[CONF_INTERVAL] = user_input[CONF_INTERVAL]
                self._data[CONF_TIMESTAMP_SOURCE] = DEFAULT_TIMESTAMP_SOURCE
                self._data[CONF_ONLY_ON_CHANGE] = DEFAULT_ONLY_ON_CHANGE
                title = self._vehicle_name or "MySkoda ABRP"
                return self.async_create_entry(title=title, data=self._data)

        schema = vol.Schema(
            {
                vol.Required(CONF_INTERVAL, default=DEFAULT_INTERVAL): NumberSelector(
                    NumberSelectorConfig(
                        min=MIN_INTERVAL,
                        max=MAX_INTERVAL,
                        step=1,
                        unit_of_measurement="s",
                        mode=NumberSelectorMode.BOX,
                    )
                )
            }
        )
        return self.async_show_form(step_id="interval", data_schema=schema, errors=errors)

    # -- Reauth: credentials were rejected at runtime --
    async def async_step_reauth(self, entry_data: Mapping[str, Any]):
        self._reauth_entry = self.hass.config_entries.async_get_entry(
            self.context["entry_id"]
        )
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}
        entry = self._reauth_entry
        assert entry is not None

        if user_input is not None:
            api_key = user_input[CONF_API_KEY].strip()
            user_token = user_input[CONF_USER_TOKEN].strip()

            soc_entity = entry.data.get(FIELD_SPECS[FIELD_SOC].config_key)
            # Fall back to a placeholder SoC if the car happens to be
            # offline right now — this call only exists to check the
            # credentials, a stale value is harmless for that purpose.
            soc_value = _current_soc(self.hass, soc_entity)
            if soc_value is None:
                soc_value = 50.0

            session = async_get_clientsession(self.hass)
            try:
                await abrp_api.validate_credentials(
                    session, api_key, user_token, soc_value, int(dt_util.utcnow().timestamp())
                )
            except abrp_api.AbrpAuthError:
                errors["base"] = "invalid_auth"
            except abrp_api.AbrpApiError:
                errors["base"] = "cannot_connect"
            else:
                new_data = {**entry.data, CONF_API_KEY: api_key, CONF_USER_TOKEN: user_token}
                self.hass.config_entries.async_update_entry(entry, data=new_data)
                await self.hass.config_entries.async_reload(entry.entry_id)
                return self.async_abort(reason="reauth_successful")

        schema = vol.Schema(
            {
                vol.Required(CONF_API_KEY): str,
                vol.Required(CONF_USER_TOKEN): str,
            }
        )
        return self.async_show_form(step_id="reauth_confirm", data_schema=schema, errors=errors)


class OptionsFlowHandler(config_entries.OptionsFlow):
    """Edit credentials, model, entity mapping, interval and fine-tuning after setup."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}
        entry = self.config_entry
        current: dict[str, Any] = {**entry.data, **entry.options}

        if user_input is not None:
            cleaned: dict[str, Any] = dict(current)
            for key, value in user_input.items():
                if value in (None, ""):
                    cleaned.pop(key, None)
                else:
                    cleaned[key] = value

            if not str(cleaned.get(CONF_API_KEY, "")).strip():
                errors[CONF_API_KEY] = "required"
            if not str(cleaned.get(CONF_USER_TOKEN, "")).strip():
                errors[CONF_USER_TOKEN] = "required"

            if not errors:
                cleaned[CONF_API_KEY] = str(cleaned[CONF_API_KEY]).strip()
                cleaned[CONF_USER_TOKEN] = str(cleaned[CONF_USER_TOKEN]).strip()
                return self.async_create_entry(title="", data=cleaned)

        schema_dict: dict[Any, Any] = {
            vol.Required(CONF_API_KEY, default=current.get(CONF_API_KEY, "")): str,
            vol.Required(CONF_USER_TOKEN, default=current.get(CONF_USER_TOKEN, "")): str,
            vol.Optional(CONF_CAR_MODEL, default=current.get(CONF_CAR_MODEL, "")): str,
            vol.Required(
                CONF_INTERVAL, default=current.get(CONF_INTERVAL, DEFAULT_INTERVAL)
            ): NumberSelector(
                NumberSelectorConfig(
                    min=MIN_INTERVAL,
                    max=MAX_INTERVAL,
                    step=1,
                    unit_of_measurement="s",
                    mode=NumberSelectorMode.BOX,
                )
            ),
            vol.Required(
                CONF_TIMESTAMP_SOURCE,
                default=current.get(CONF_TIMESTAMP_SOURCE, DEFAULT_TIMESTAMP_SOURCE),
            ): SelectSelector(
                SelectSelectorConfig(
                    options=[
                        SelectOptionDict(
                            label="Vehicle measurement time", value=TIMESTAMP_SOURCE_VEHICLE
                        ),
                        SelectOptionDict(
                            label="Time of sending", value=TIMESTAMP_SOURCE_SEND_TIME
                        ),
                    ],
                    mode=SelectSelectorMode.DROPDOWN,
                )
            ),
            vol.Required(
                CONF_ONLY_ON_CHANGE,
                default=current.get(CONF_ONLY_ON_CHANGE, DEFAULT_ONLY_ON_CHANGE),
            ): BooleanSelector(),
        }
        schema_dict.update(_entity_field_schema(self.hass, current.get(CONF_VEHICLE_DEVICE_ID), current))

        return self.async_show_form(
            step_id="init", data_schema=vol.Schema(schema_dict), errors=errors
        )

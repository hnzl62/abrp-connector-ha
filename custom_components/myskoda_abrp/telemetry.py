"""Builds ABRP telemetry payloads from MySkoda entity states and sends them."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import logging
import time
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, HomeAssistant, State, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.debounce import Debouncer
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import (
    async_call_later,
    async_track_state_change_event,
    async_track_time_interval,
)
from homeassistant.util import dt as dt_util

from . import abrp_api
from .const import (
    BACKOFF_STEPS,
    CHARGE_TYPE_DC_VALUES,
    CHARGING_STATE_ACTIVE_VALUES,
    DEBOUNCE_SECONDS,
    FIELD_CHARGE_TYPE,
    FIELD_CHARGING_POWER,
    FIELD_CHARGING_STATE,
    FIELD_EXT_TEMP,
    FIELD_IN_MOTION,
    FIELD_ODOMETER,
    FIELD_RANGE,
    FIELD_SOC,
    FIELD_TIMESTAMP,
    MIN_SEND_INTERVAL_SECONDS,
    TIMESTAMP_SOURCE_VEHICLE,
    signal_update,
)

_LOGGER = logging.getLogger(__name__)

UNAVAILABLE_STATES = ("unknown", "unavailable", "")

# Entities that, when they change, justify an immediate send instead of
# waiting for the next heartbeat.
TRIGGER_FIELDS = (
    FIELD_SOC,
    FIELD_CHARGING_STATE,
    FIELD_CHARGING_POWER,
    FIELD_CHARGE_TYPE,
)


def _state_or_none(hass: HomeAssistant, entity_id: str | None) -> State | None:
    if not entity_id:
        return None
    state = hass.states.get(entity_id)
    if state is None or state.state in UNAVAILABLE_STATES:
        return None
    return state


def _as_float(state: State | None) -> float | None:
    if state is None:
        return None
    try:
        return float(state.state)
    except (TypeError, ValueError):
        return None


def _now_utc() -> int:
    return int(datetime.now(tz=timezone.utc).timestamp())


def _parse_utc(state: State | None) -> int | None:
    if state is None:
        return None
    parsed = dt_util.parse_datetime(state.state)
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return int(parsed.timestamp())


class TelemetrySender:
    """Owns the send loop that pushes MySkoda entity states to ABRP."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        api_key: str,
        user_token: str,
        car_model: str | None,
        entity_map: dict[str, str],
        interval: int,
        timestamp_source: str,
        only_on_change: bool,
    ) -> None:
        self.hass = hass
        self._entry = entry
        self._api_key = api_key
        self._user_token = user_token
        self._car_model = car_model
        self._entity_map = entity_map
        self._interval = interval
        self._timestamp_source = timestamp_source
        self._only_on_change = only_on_change

        self.enabled = True

        # Public diagnostic state, read directly by sensor entities.
        self.last_success_at: datetime | None = None
        self.last_payload: dict[str, Any] | None = None
        self.last_error: str | None = None

        self._unsub_interval: Any = None
        self._unsub_state: Any = None
        self._unsub_backoff: Any = None
        self._debouncer: Debouncer | None = None
        self._last_sent_monotonic: float = -MIN_SEND_INTERVAL_SECONDS
        self._backoff_index = -1
        self._send_lock = asyncio.Lock()

    @callback
    def async_start(self) -> None:
        """Register the heartbeat interval and state-change listeners."""
        self._unsub_interval = async_track_time_interval(
            self.hass, self._handle_interval, timedelta(seconds=self._interval)
        )

        trigger_entities = [
            eid
            for key in TRIGGER_FIELDS
            if (eid := self._entity_map.get(key)) is not None
        ]
        if trigger_entities:
            self._debouncer = Debouncer(
                self.hass,
                _LOGGER,
                cooldown=DEBOUNCE_SECONDS,
                immediate=False,
                function=self._debounced_send,
            )
            self._unsub_state = async_track_state_change_event(
                self.hass, trigger_entities, self._handle_state_change
            )

    @callback
    def async_stop(self) -> None:
        """Remove all listeners and cancel any pending backoff retry."""
        if self._unsub_interval:
            self._unsub_interval()
            self._unsub_interval = None
        if self._unsub_state:
            self._unsub_state()
            self._unsub_state = None
        if self._unsub_backoff:
            self._unsub_backoff()
            self._unsub_backoff = None

    @callback
    def _handle_interval(self, _now: datetime) -> None:
        self.hass.async_create_task(self.async_send_now("interval"))

    @callback
    def _handle_state_change(self, _event: Event) -> None:
        if self._debouncer:
            self.hass.async_create_task(self._debouncer.async_call())

    async def _debounced_send(self) -> None:
        await self.async_send_now("state_change")

    def build_payload(self) -> dict[str, Any] | None:
        """Build the ABRP tlm payload from current entity states.

        Returns ``None`` if no valid State of Charge is available, since
        ``soc`` is the one field ABRP requires on every request.
        """
        hass = self.hass
        payload: dict[str, Any] = {}

        soc = _as_float(_state_or_none(hass, self._entity_map.get(FIELD_SOC)))
        if soc is None:
            return None
        payload[FIELD_SOC] = soc

        if self._timestamp_source == TIMESTAMP_SOURCE_VEHICLE:
            ts_state = _state_or_none(hass, self._entity_map.get(FIELD_TIMESTAMP))
            payload["utc"] = _parse_utc(ts_state) or _now_utc()
        else:
            payload["utc"] = _now_utc()

        charging_state = _state_or_none(hass, self._entity_map.get(FIELD_CHARGING_STATE))
        is_charging = bool(
            charging_state is not None
            and charging_state.state.lower() in CHARGING_STATE_ACTIVE_VALUES
        )
        payload["is_charging"] = 1 if is_charging else 0

        # Skoda has no meaningful "power" while not charging, so we only
        # send it while is_charging is true rather than falsely reporting 0kW.
        if is_charging:
            power = _as_float(_state_or_none(hass, self._entity_map.get(FIELD_CHARGING_POWER)))
            if power is not None:
                payload["power"] = -abs(power)

            charge_type = _state_or_none(hass, self._entity_map.get(FIELD_CHARGE_TYPE))
            if charge_type is not None:
                payload["is_dcfc"] = (
                    1 if charge_type.state.lower() in CHARGE_TYPE_DC_VALUES else 0
                )

        motion = _state_or_none(hass, self._entity_map.get(FIELD_IN_MOTION))
        if motion is not None:
            payload["is_parked"] = 0 if motion.state == "on" else 1

        odometer = _as_float(_state_or_none(hass, self._entity_map.get(FIELD_ODOMETER)))
        if odometer is not None:
            payload["odometer"] = odometer

        est_range = _as_float(_state_or_none(hass, self._entity_map.get(FIELD_RANGE)))
        if est_range is not None:
            payload["est_battery_range"] = est_range

        ext_temp = _as_float(_state_or_none(hass, self._entity_map.get(FIELD_EXT_TEMP)))
        if ext_temp is not None:
            payload["ext_temp"] = ext_temp

        if self._car_model:
            payload["car_model"] = self._car_model

        return payload

    async def async_send_now(self, reason: str) -> None:
        """Build a payload and send it, honoring the enabled flag and rate limits."""
        if not self.enabled or self._unsub_backoff is not None:
            return

        async with self._send_lock:
            now = time.monotonic()
            if now - self._last_sent_monotonic < MIN_SEND_INTERVAL_SECONDS:
                return

            payload = self.build_payload()
            if payload is None:
                _LOGGER.debug("Skipping ABRP send (%s): no valid SoC available", reason)
                return

            if self._only_on_change and self._payload_unchanged(payload):
                _LOGGER.debug("Skipping ABRP send (%s): payload unchanged", reason)
                return

            session = async_get_clientsession(self.hass)
            try:
                await abrp_api.send_telemetry(
                    session, self._api_key, self._user_token, payload
                )
            except abrp_api.AbrpAuthError as err:
                self._last_sent_monotonic = now
                self._record_error(str(err))
                self._entry.async_start_reauth(self.hass)
                return
            except abrp_api.AbrpApiError as err:
                self._last_sent_monotonic = now
                _LOGGER.warning("ABRP telemetry send failed: %s", err)
                self._record_error(str(err))
                self._schedule_backoff()
                return

            self._last_sent_monotonic = now
            self._backoff_index = -1
            _LOGGER.debug("Sent ABRP telemetry (%s): %s", reason, payload)
            self._record_success(payload)

    def _payload_unchanged(self, payload: dict[str, Any]) -> bool:
        if self.last_payload is None:
            return False
        compare_keys = (set(payload) | set(self.last_payload)) - {"utc"}
        return all(payload.get(k) == self.last_payload.get(k) for k in compare_keys)

    def _schedule_backoff(self) -> None:
        self._backoff_index = min(self._backoff_index + 1, len(BACKOFF_STEPS) - 1)
        delay = BACKOFF_STEPS[self._backoff_index]

        @callback
        def _retry(_now: datetime) -> None:
            self._unsub_backoff = None
            self.hass.async_create_task(self.async_send_now("backoff_retry"))

        self._unsub_backoff = async_call_later(self.hass, delay, _retry)

    def _record_success(self, payload: dict[str, Any]) -> None:
        self.last_success_at = dt_util.utcnow()
        self.last_payload = payload
        self.last_error = None
        async_dispatcher_send(self.hass, signal_update(self._entry.entry_id))

    def _record_error(self, error: str) -> None:
        self.last_error = error
        async_dispatcher_send(self.hass, signal_update(self._entry.entry_id))

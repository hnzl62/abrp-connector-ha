"""Constants for the MySkoda → ABRP Telemetry integration."""
from __future__ import annotations

from dataclasses import dataclass, field

from homeassistant.const import Platform

DOMAIN = "myskoda_abrp"
MYSKODA_DOMAIN = "myskoda"

MANUFACTURER = "MySkoda → ABRP"

# --- ABRP API ---
ABRP_API_BASE = "https://api.iternio.com/1"
ABRP_SEND_URL = f"{ABRP_API_BASE}/tlm/send"
ABRP_CARMODELS_URL = f"{ABRP_API_BASE}/tlm/get_carmodels_list"

# --- Config entry keys ---
CONF_API_KEY = "api_key"
CONF_USER_TOKEN = "user_token"
CONF_VEHICLE_DEVICE_ID = "vehicle_device_id"
CONF_CAR_MODEL = "car_model"
CONF_INTERVAL = "interval"
CONF_TIMESTAMP_SOURCE = "timestamp_source"
CONF_ONLY_ON_CHANGE = "only_on_change"

# Per-field entity mapping config keys, e.g. "entity_soc", "entity_charging_power", ...
ENTITY_KEY_PREFIX = "entity_"

# --- Timestamp source options ---
TIMESTAMP_SOURCE_VEHICLE = "vehicle"
TIMESTAMP_SOURCE_SEND_TIME = "send_time"
DEFAULT_TIMESTAMP_SOURCE = TIMESTAMP_SOURCE_VEHICLE

# --- Defaults / timing ---
DEFAULT_INTERVAL = 300
MIN_INTERVAL = 30
MAX_INTERVAL = 3600
DEFAULT_ONLY_ON_CHANGE = False

DEBOUNCE_SECONDS = 10
MIN_SEND_INTERVAL_SECONDS = 5

# Exponential backoff steps (seconds) applied after consecutive send failures.
BACKOFF_STEPS: tuple[int, ...] = (10, 20, 40, 300)

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.SWITCH]


@dataclass(frozen=True)
class FieldSpec:
    """Describes one ABRP telemetry field and where to auto-detect it from MySkoda."""

    config_key: str
    platform: Platform
    # Candidate entity_id / unique_id suffixes to try, in priority order.
    suffixes: tuple[str, ...]
    required: bool = False
    label: str = ""


# Field keys used internally (also used as suffix of the config key: f"entity_{key}")
FIELD_SOC = "soc"
FIELD_TIMESTAMP = "timestamp"
FIELD_CHARGING_STATE = "charging_state"
FIELD_CHARGING_POWER = "charging_power"
FIELD_CHARGE_TYPE = "charge_type"
FIELD_IN_MOTION = "in_motion"
FIELD_ODOMETER = "odometer"
FIELD_RANGE = "range"
FIELD_EXT_TEMP = "ext_temp"

# Ordered so the config flow can render them consistently.
FIELD_SPECS: dict[str, FieldSpec] = {
    FIELD_SOC: FieldSpec(
        config_key=f"{ENTITY_KEY_PREFIX}{FIELD_SOC}",
        platform=Platform.SENSOR,
        suffixes=("battery_percentage",),
        required=True,
        label="State of Charge",
    ),
    FIELD_TIMESTAMP: FieldSpec(
        config_key=f"{ENTITY_KEY_PREFIX}{FIELD_TIMESTAMP}",
        platform=Platform.SENSOR,
        suffixes=("car_captured",),
        required=False,
        label="Vehicle data timestamp",
    ),
    FIELD_CHARGING_STATE: FieldSpec(
        config_key=f"{ENTITY_KEY_PREFIX}{FIELD_CHARGING_STATE}",
        platform=Platform.SENSOR,
        suffixes=("charging_state",),
        required=False,
        label="Charging state",
    ),
    FIELD_CHARGING_POWER: FieldSpec(
        config_key=f"{ENTITY_KEY_PREFIX}{FIELD_CHARGING_POWER}",
        platform=Platform.SENSOR,
        suffixes=("charging_power",),
        required=False,
        label="Charging power",
    ),
    FIELD_CHARGE_TYPE: FieldSpec(
        config_key=f"{ENTITY_KEY_PREFIX}{FIELD_CHARGE_TYPE}",
        platform=Platform.SENSOR,
        suffixes=("charge_type",),
        required=False,
        label="Charge type (AC/DC)",
    ),
    FIELD_IN_MOTION: FieldSpec(
        config_key=f"{ENTITY_KEY_PREFIX}{FIELD_IN_MOTION}",
        platform=Platform.BINARY_SENSOR,
        suffixes=("vehicle_in_motion",),
        required=False,
        label="Vehicle in motion",
    ),
    FIELD_ODOMETER: FieldSpec(
        config_key=f"{ENTITY_KEY_PREFIX}{FIELD_ODOMETER}",
        platform=Platform.SENSOR,
        suffixes=("milage", "overall_mileage"),
        required=False,
        label="Odometer",
    ),
    FIELD_RANGE: FieldSpec(
        config_key=f"{ENTITY_KEY_PREFIX}{FIELD_RANGE}",
        platform=Platform.SENSOR,
        suffixes=("electric_range", "range"),
        required=False,
        label="Estimated range",
    ),
    FIELD_EXT_TEMP: FieldSpec(
        config_key=f"{ENTITY_KEY_PREFIX}{FIELD_EXT_TEMP}",
        platform=Platform.SENSOR,
        suffixes=("outside_temperature",),
        required=False,
        label="Outside temperature",
    ),
}

# MySkoda entity state values used to interpret charging_state / charge_type sensors.
CHARGING_STATE_ACTIVE_VALUES = {"charging"}
CHARGE_TYPE_DC_VALUES = {"dc"}

# Diagnostic entity attribute keys
ATTR_LAST_PAYLOAD = "last_payload"


def signal_update(entry_id: str) -> str:
    """Dispatcher signal fired whenever a telemetry send attempt completes."""
    return f"{DOMAIN}_update_{entry_id}"

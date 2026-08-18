"""Async client for the Iternio / ABRP Telemetry API.

API documentation: https://documenter.getpostman.com/view/7396339/SWTK5a8w
"""
from __future__ import annotations

import json
import logging
from typing import Any

import aiohttp

from .const import ABRP_CARMODELS_URL, ABRP_SEND_URL

_LOGGER = logging.getLogger(__name__)

REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=15)


class AbrpError(Exception):
    """Base error for ABRP API failures."""


class AbrpAuthError(AbrpError):
    """Raised when the API key or user token is rejected by ABRP."""


class AbrpApiError(AbrpError):
    """Raised for any other non-successful API response."""


async def fetch_car_models(
    session: aiohttp.ClientSession,
) -> dict[str, dict[str, str]]:
    """Fetch the public ABRP car model list, grouped by manufacturer.

    Returns ``{manufacturer: {display_label: model_id}}``. This endpoint is
    public and does not require an API key.
    """
    try:
        async with session.get(ABRP_CARMODELS_URL, timeout=REQUEST_TIMEOUT) as resp:
            if resp.status != 200:
                raise AbrpApiError(
                    f"Unexpected status {resp.status} fetching car models"
                )
            data = await resp.json(content_type=None)
    except aiohttp.ClientError as err:
        raise AbrpApiError(f"Connection error fetching car models: {err}") from err

    if data.get("status") != "ok":
        raise AbrpApiError(f"Car model list request failed: {data}")

    grouped: dict[str, dict[str, str]] = {}
    for entry in data.get("result", []):
        for display_name, model_id in entry.items():
            parts = [p.strip() for p in display_name.split(";")]
            if len(parts) > 1:
                manufacturer, model_label = parts[0], " ".join(parts[1:])
            else:
                manufacturer, model_label = "Other", display_name.strip()
            grouped.setdefault(manufacturer, {})[model_label] = model_id

    return grouped


async def send_telemetry(
    session: aiohttp.ClientSession,
    api_key: str,
    token: str,
    tlm: dict[str, Any],
) -> dict[str, Any]:
    """Send one telemetry payload to ABRP.

    Raises ``AbrpAuthError`` if the credentials are rejected, or
    ``AbrpApiError`` for any other failure. Returns the decoded JSON body
    on success (``{"status": "ok"}``).
    """
    headers = {"Authorization": f"APIKEY {api_key}"}
    params = {"token": token, "tlm": json.dumps(tlm)}

    try:
        async with session.post(
            ABRP_SEND_URL, headers=headers, params=params, timeout=REQUEST_TIMEOUT
        ) as resp:
            if resp.status in (401, 403):
                raise AbrpAuthError(f"ABRP rejected credentials (HTTP {resp.status})")
            if resp.status != 200:
                body = await resp.text()
                raise AbrpApiError(f"ABRP returned HTTP {resp.status}: {body}")
            data = await resp.json(content_type=None)
    except aiohttp.ClientError as err:
        raise AbrpApiError(f"Connection error sending telemetry: {err}") from err

    if data.get("status") != "ok":
        raise AbrpApiError(f"ABRP reported failure: {data}")

    return data


async def validate_credentials(
    session: aiohttp.ClientSession,
    api_key: str,
    token: str,
    soc: float,
    utc: int,
) -> None:
    """Validate an API key + user token pair against the live API.

    Sends a minimal real payload (utc + soc) so a bad token fails during
    the config flow instead of silently failing later. Raises
    ``AbrpAuthError``/``AbrpApiError`` on failure.
    """
    await send_telemetry(session, api_key, token, {"utc": utc, "soc": soc})

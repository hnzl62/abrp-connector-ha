# MySkoda → ABRP Telemetry

A Home Assistant custom integration that forwards vehicle data from the [MySkoda integration](https://github.com/skodaconnect/homeassistant-myskoda) to the [ABRP (A Better Routeplanner) Telemetry API](https://documenter.getpostman.com/view/7396339/SWTK5a8w).

The API key, user token, ABRP vehicle model, Home Assistant entity mapping, and send interval are configured through the Home Assistant UI.

## What it does

- Reads battery state of charge, charging state, charging power, AC/DC charging type, odometer, estimated range, and outside temperature from MySkoda entities.
- Sends telemetry periodically and also sends a debounced update when charging-related entities or the state of charge change.
- Provides diagnostic entities showing the last successful payload and the last error.
- Provides a switch to pause and resume telemetry without removing the integration.
- Supports changing credentials, entity mappings, the ABRP model, and timing later through **Settings → Devices & services → Configure**.

## Important limitations

- **No live GPS while driving.** MySkoda does not provide the required live driving position through this integration, so `lat` and `lon` are never sent.
- **This is not a 10-second live-telemetry solution.** The connector can send as often as every 30 seconds, but the freshness of the values depends on when MySkoda updates the vehicle entities.
- **The default heartbeat is every 300 seconds (5 minutes).** The current UI accepts an interval from 30 to 3600 seconds. Charging-related state changes can trigger an additional send after a short debounce period.
- **Realistic use:** keeping ABRP's state of charge and vehicle information reasonably current for route planning and recording charging data. It is not intended to replace an ABRP live-data dongle or a native live vehicle connection.

## Requirements

- Home Assistant 2024.12 or newer
- The [MySkoda Home Assistant integration](https://github.com/skodaconnect/homeassistant-myskoda), configured with at least one vehicle
- An ABRP account
- An ABRP telemetry API key and user token

## Installation

### HACS (recommended)

1. Open HACS.
2. Open the three-dot menu in the upper-right corner and select **Custom repositories**.
3. Add this repository URL and choose **Integration** as the category:

   ```text
   https://github.com/hnzl62/abrp-connector-ha
   ```

4. Install **MySkoda → ABRP Telemetry**.
5. Restart Home Assistant.

For a fork, use your own repository URL instead.

### Manual installation

Copy [`custom_components/myskoda_abrp`](custom_components/myskoda_abrp) into:

```text
<home-assistant-config>/custom_components/myskoda_abrp
```

Then restart Home Assistant. Manual installations must be updated by copying the folder again.

## Setup

1. Create an ABRP telemetry API key at [ABRP API resources](https://abetterrouteplanner.com/resources/api). A telemetry-only key is sufficient.
2. Obtain the ABRP user token from the ABRP web or mobile app under the vehicle's **Live Data Setup** / **Generic** section.
3. In Home Assistant, open **Settings → Devices & services → Add integration**.
4. Search for **MySkoda → ABRP Telemetry**.
5. Enter the API key and user token.
6. Select the MySkoda vehicle.
7. Select the closest ABRP manufacturer and vehicle model.
8. Review the entity mapping. The state-of-charge entity is required; the other fields are optional.
9. Choose the send interval in seconds.

The integration tries to pre-select MySkoda entities automatically. Review the selections because entity names can differ between MySkoda versions or vehicle models.

## Telemetry timing

The connector sends:

- A periodic heartbeat at the configured interval, defaulting to every 5 minutes.
- An additional update when state of charge, charging state, charging power, or AC/DC charge type changes.
- Change-triggered sends after a debounce period of approximately 10 seconds.
- No more than one request every 5 seconds.

The **Only send heartbeat when the payload changed** option can suppress periodic sends when all telemetry values other than the timestamp are unchanged.

## Data sent to ABRP

| ABRP field | MySkoda source | Condition or transformation |
|---|---|---|
| `soc` | Battery percentage | Required; no request is sent without a valid value |
| `utc` | Vehicle data timestamp or current time | Selectable in the options flow |
| `is_charging` | Charging-state sensor | `1` when the state is `charging`, otherwise `0` |
| `power` | Charging-power sensor | Sent only while charging and sent as a negative absolute value |
| `is_dcfc` | Charge-type sensor | `1` when the value is `dc`, otherwise `0` |
| `is_parked` | Vehicle-in-motion binary sensor | Inverted: moving is `0`, not moving is `1` |
| `odometer` | Odometer sensor | Optional |
| `est_battery_range` | Estimated-range sensor | Optional |
| `ext_temp` | Outside-temperature sensor | Optional |
| `car_model` | Selected configuration value | Optional |

The integration does not send `lat`, `lon`, `speed`, `voltage`, `current`, `batt_temp`, `soh`, `heading`, `elevation`, tire-pressure data, or HVAC fields.

## Diagnostics

The integration creates a service device with:

- `Last successful send`: timestamp of the last payload accepted by ABRP. The last payload is available as an attribute.
- `Last error`: the most recent failed-send error, or `ok`.
- `Telemetry enabled`: a switch for pausing and resuming uploads.

Authentication failures start Home Assistant's re-authentication flow. Other API failures use increasing retry delays.

## Security notes

- API credentials are entered through Home Assistant's config flow; do not commit them to YAML, Git, or issue reports.
- This integration sends telemetry to ABRP over HTTPS.
- The repository's CI workflow validates the Home Assistant and HACS metadata. It does not require vehicle credentials.

## License

[MIT](LICENSE)

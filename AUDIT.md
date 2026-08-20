# Audit notes

This fork was reviewed before publishing the `english-audit` branch.

## Scope

- Home Assistant config flow and options flow
- ABRP HTTP client and credential handling
- Telemetry scheduling, throttling, retry, and payload construction
- Entity mapping and diagnostic entities
- HACS and Hassfest metadata
- Repository CI workflow and credential exposure
- Documentation accuracy

## Changes made

- Replaced the German README with English installation, setup, timing, payload, limitation, and security documentation.
- Fixed re-authentication so newly entered ABRP credentials update both the original config data and the options data. This prevents stale credentials in `entry.options` from overriding the repaired credentials after a reload.
- Pinned GitHub Actions to immutable commit SHAs instead of following mutable branches or tags.
- Corrected the documented send interval to match the current implementation: 30–3600 seconds, default 300 seconds.

## Checks performed

- Python bytecode compilation of `custom_components` passed.
- JSON syntax validation for all integration JSON files passed.
- Git whitespace/error check passed.
- No credentials or hard-coded tokens were found in the repository.

## Remaining operational limitations

- The integration depends on the freshness and availability of MySkoda entity states.
- It does not provide live GPS or high-frequency driving telemetry.
- Live ABRP API validation requires real credentials and was not performed during this repository audit.
- The repository has no dedicated automated unit-test suite; Home Assistant and HACS validation are delegated to GitHub Actions.

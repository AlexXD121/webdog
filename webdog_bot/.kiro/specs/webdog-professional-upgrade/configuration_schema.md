# WebDog Professional - Configuration Schema

## Overview
The configuration system allows "Power-User" control over the monitoring engine. Settings can be applied Globally (affecting all monitors) or Per-Monitor (overriding global defaults).

## Data Structure: `Config`

| Field | Type | Default | Validation Rules | Description |
|---|---|---|---|---|
| `similarity_threshold` | float | 0.85 (85%) | 0.0 < x <= 1.0 | Sensitivity of the similarity engine. Lower values = less sensitive to changes. |
| `check_interval` | int | 60 (seconds) | >= 30 | Frequency of patrol checks. Enforced minimum of 30s to prevent abuse. |
| `include_diff` | bool | True | N/A | If True, alerts include a visual text diff of changes. |
| `custom_selector` | string | None | N/A | Optional CSS selector to target specific page elements (Not yet exposed in UI). |

## Hierarchy Resolution
When patrolling a URL, the system resolves configuration in this order:
1. **Monitor-Specific Config**: If `monitor.config` exists, it is used.
2. **Global User Config**: If no monitor-specific config overrides, `user_data.user_config` is used.

## Validation Logic
- **Interval Clamping**: Any attempt to set `check_interval` below 30s is automatically corrected to 30s.
- **Threshold Clamping**: Values > 1.0 are set to 1.0. Values <= 0.0 are set to 0.01.

## Persistence
Configuration is stored as a nested JSON object within the `UserData` and `Monitor` schemas inside the atomic `webdog_state.json`.

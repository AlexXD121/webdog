# Governance Rules & Constants

## Rate Limits
| Scope | Limit | Implementation |
|---|---|---|
| **Global Web Fetching** | **5 RPS** | Token Bucket (Capacity 5, Refill 5/s) |
| **Telegram API** | **30 Msg/s** | Leaky Bucket Queue (Drain Rate 25/s safety margin) |

## Burst Handling
- Web requests allow a burst of **5** (Instant execution) before throttling kicks in.
- Telegram notifications are **Queued** indefinitely until drained to prevent data loss.

## Adaptive Protection
- If Telegram Queue Depth > 50: `GlobalGovernor.is_congested` returns True.
- (Future): Patrol Engine checks congestion before scheduling new checks.

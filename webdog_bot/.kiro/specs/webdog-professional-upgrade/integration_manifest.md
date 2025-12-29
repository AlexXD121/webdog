# WebDog Professional - Integration Manifest

## 1. System Architecture
The WebDog Professional Bot is orchestrated by the `WebDogBot` class (Singleton Controller), which manages the lifecycle of five core components:
1.  **AtomicDatabaseManager**: Handles thread-safe, resilient JSON storage.
2.  **GlobalRequestManager**: Manages all outbound HTTP traffic with strict rate limiting (5 RPS) and browser stealth.
3.  **GovernanceEngine (Governor)**: Enforces limits and Congestion Control.
4.  **ForensicFingerprinter**: Analyzes content changes.
5.  **MetricsTracker**: Monitors system health and performance.

## 2. Boot Sequence (`startup()`)
1.  **Environment Validation**: Checks for `TELEGRAM_TOKEN` and `.env` file.
2.  **Storage Guard**: Verifies `db.json` existence and checks available disk space (>10MB).
3.  **Component Init**: Warm-up of RequestManager loops and Database write workers.
4.  **Telegram Connect**: Initializes `Application`, registers Handlers (`/watch`, Callbacks), and starts the Polling loop.

## 3. Patrol Logic (`JobBasedDataLoader`)
- **Interval**: 60 Seconds.
- **Congestion Check**: If `Governor.is_congested` (Telegram Queue > 50), the *entire* patrol cycle is skipped to prevent cascade failure.
- **On-Demand Loading**: Iterates through Monitors in memory; Config and History are accessed properties.
- **Execution Flow**:
    1.  Check Snooze/Interval.
    2.  `Acquire Token` (Blocking wait for global RPS).
    3.  `Fetch URL`.
    4.  `Generate Fingerprint`.
    5.  `Compare` -> `Calculate Similarity`.
    6.  `Alert` (if Score < Threshold) -> `Queue to Telegram Throttler`.
    7.  `Archive` history if needed.

## 4. Shutdown Protocol (`shutdown()`)
Triggered by `SIGINT` (Ctrl+C) or internal error.
1.  **Stop Polling**: Telegram updates cease.
2.  **Close Network**: `RequestManager` terminates `httpx` sessions.
3.  **Stop Throttler**: Telegram Governor stops accepting new messages.
4.  **Flush DB**: Ensures any pending atomic writes complete (best effort).
5.  **Exit**: Process terminates with status 0.

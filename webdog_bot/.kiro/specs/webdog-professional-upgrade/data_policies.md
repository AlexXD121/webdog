# Data Retention & Export Policies

## 1. Change History
- **Retention Period**: 30 Days.
- **Pruning Logic**: Automatic pruning occurs on every new entry add. Entries older than 30 days are permanently deleted from the active log.
- **Storage**: Lightweight `HistoryEntry` JSON objects stored within the main `Monitor` record.

## 2. Data Export
- **Formats**: CSV (Excel-compatible) and JSON (Raw Data).
- **Security**: Export files are generated on-demand in the `exports/` directory.
- **Cleanup**: Files should be treated as temporary. (Future: Auto-delete cron job).

## 3. Forensic Snapshots (Advanced)
- *Note*: Unlike the lightweight history log, full content snapshots are stored separately and compressed using zlib. Their retention policy is separate (currently manual or capacity-based, not date-based in this task).

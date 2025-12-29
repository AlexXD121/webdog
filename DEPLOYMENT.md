# WebDog Professional - Deployment Guide

## System Requirements

### Hardware / Virtual Machine
For running **1,000 Monitors**:
- **CPU**: 2 vCPUs (Python is single-threaded, but AsyncIO benefits from raw core speed).
- **RAM**: 2GB Minimum (4GB Recommended). 
  - *Baseline Memory*: ~150MB.
  - *Per 1k Monitors*: ~50MB overhead during patrol.
- **Disk**: 20GB SSD.
  - *DB Size*: ~10MB per 1k monitors.
  - *History Logs*: Can grow to ~1GB over 30 days depending on change frequency.
  - *Logs*: Rotation required.

### Software
- **OS**: Linux (Ubuntu 22.04 LTS recommended) or Windows Server.
- **Python**: 3.9+ (Tested on 3.10).
- **Dependencies**: See `requirements.txt`.

## Environment Configuration
Protect your credentials by using environment variables. Do NOT commit `.env` to git.

```ini
# .env file
TELEGRAM_TOKEN=123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11
# Optional: Admin ID for critical alerts
ADMIN_ID=123456789
```

## Installation
1. **Clone**: `git clone <repo>`
2. **Virtual Env**:
   ```bash
   python -m venv venv
   source venv/bin/activate  # Linux
   .\venv\Scripts\activate   # Windows
   ```
3. **Install**:
   ```bash
   pip install -r requirements.txt
   ```

## Running in Production
Do not run with `python main.py` in a detached shell. Use a process manager like **Systemd** or **Docker**.

### Systemd Service (`/etc/systemd/system/webdog.service`)
```ini
[Unit]
Description=WebDog Professional
After=network.target

[Service]
User=webdog
WorkingDirectory=/opt/webdog
ExecStart=/opt/webdog/venv/bin/python /opt/webdog/webdog_bot/main.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

## Maintenance

### Log Rotation
The bot generates `webdog.log`. Configure `logrotate` to prevent disk overflow.
```
/opt/webdog/webdog.log {
    daily
    rotate 7
    compress
    missingok
    notifempty
}
```

### Database Backups
`AtomicDatabaseManager` creates `.bak` files automatically.
Weekly off-site backups of `webdog_db.json` are recommended.
```bash
# Crontab example (Weekly)
0 3 * * 0 cp /opt/webdog/webdog_db.json /backups/webdog_$(date +\%F).json
```

## Troubleshooting
- **Bot Stuck?**: Check CPU usage. If 100%, reduce Patrol frequency.
- **Telegram Errors?**: Check `governor` logs for congestion. The bot will auto-throttle.
- **DB Corruption?**: Rename `webdog_db.json.bak` to `webdog_db.json` to restore previous state.

# Host Healthcheck Monitor

A simple systemd-based monitor that pings healthchecks.io every 15 seconds to verify the Raspberry Pi host is alive and reachable.

## Purpose

This monitor serves a different purpose than the gardener agent healthcheck:
- **Host monitor** (this): Verifies the Raspberry Pi is powered on and has network connectivity
- **Agent healthcheck**: Verifies the gardener agent successfully executes every 10 minutes

By monitoring both, we can distinguish between:
1. Host is down (no pings from host monitor)
2. Host is up but agent is failing (host pings arrive, but no agent pings)

## Design

### Architecture
- **systemd timer**: Triggers service every 15 seconds
- **systemd service**: Executes a simple curl command to ping healthchecks.io
- **Frequency**: 4 pings/minute (well under healthchecks.io's 5/minute limit)
- **Logging**: Only errors logged to journalctl

### Design Principles (KISS + YAGNI)
- URL configured at install time (no runtime configuration needed)
- No retry logic (next ping is only 15s away)
- No disk logging (journalctl is sufficient)
- System-wide service (not user-specific)
- DynamicUser for security (no dedicated user needed)

### Why systemd timer instead of cron?
- **Precise timing**: Systemd timers can run sub-minute intervals precisely
- **Better logging**: Built-in integration with journalctl
- **No overlap**: Systemd prevents timer from triggering if previous run still active
- **Survives reboot**: Automatically starts on boot with `WantedBy=timers.target`

## Installation

### Prerequisites
- Raspberry Pi running Raspbian/Debian with systemd
- curl installed: `sudo apt-get install curl`
- Root/sudo access
- Healthchecks.io check URL or UUID

### Install
```bash
# Using full URL
sudo bash host-monitor/install-monitor.sh https://hc-ping.com/your-uuid-here

# Or using just the UUID (automatically constructs full URL)
sudo bash host-monitor/install-monitor.sh your-uuid-here
```

The script will:
1. Validate prerequisites (curl installed, files present)
2. Substitute your healthcheck URL into the service file
3. Install service and timer to `/etc/systemd/system/`
4. Enable timer (starts on boot)
5. Start timer immediately

**Security Note**: The healthcheck URL is configured at install time and embedded in the systemd service file. The template file in git contains a placeholder (`__HEALTHCHECK_URL__`), keeping your actual URL private.

### Verify Installation
```bash
# Check timer is active and when next ping is scheduled
systemctl list-timers host-healthcheck.timer

# View recent service executions (should show success every 15s)
journalctl -u host-healthcheck.service --since "5 minutes ago"

# Check timer status
systemctl status host-healthcheck.timer
```

## Monitoring

### Healthchecks.io Dashboard
Monitor host status at your healthchecks.io dashboard URL (the URL you provided during installation).

Expected behavior:
- **Status: UP** - Pings arriving every 15 seconds
- **Status: DOWN** - No pings for >1 minute (indicates host is down or network issue)

### Local Monitoring
```bash
# Watch service logs in real-time (Ctrl+C to exit)
journalctl -u host-healthcheck.service -f

# Check timer status
systemctl status host-healthcheck.timer

# List all timers (including next trigger time)
systemctl list-timers
```

## Troubleshooting

### Timer not triggering
```bash
# Check timer is enabled and active
systemctl status host-healthcheck.timer

# If not active, start it
sudo systemctl start host-healthcheck.timer

# If not enabled, enable it
sudo systemctl enable host-healthcheck.timer
```

### Service failing
```bash
# View recent failures
journalctl -u host-healthcheck.service --since "1 hour ago"

# Test service manually
sudo systemctl start host-healthcheck.service

# Check service status
systemctl status host-healthcheck.service
```

### Network connectivity issues
```bash
# Test healthcheck URL manually (replace with your URL)
curl -v https://hc-ping.com/your-uuid-here

# Check DNS resolution
nslookup hc-ping.com

# Check internet connectivity
ping -c 3 8.8.8.8
```

## Uninstall

```bash
# Stop and disable timer
sudo systemctl disable --now host-healthcheck.timer

# Remove service files
sudo rm /etc/systemd/system/host-healthcheck.service
sudo rm /etc/systemd/system/host-healthcheck.timer

# Reload systemd
sudo systemctl daemon-reload
```

## Technical Details

### Files
- `host-healthcheck.service` - Systemd service (oneshot execution)
- `host-healthcheck.timer` - Systemd timer (15-second interval)
- `install-monitor.sh` - Idempotent installation script

### Service Configuration
- **Type**: `oneshot` - Runs once per timer trigger, exits immediately
- **ExecStart**: `/usr/bin/curl -m 10 -fsS [URL]`
  - `-m 10`: 10-second timeout
  - `-f`: Fail silently on HTTP errors
  - `-sS`: Silent mode, but show errors
- **StandardOutput**: `null` - No logging on success (reduces journal spam)
- **StandardError**: `journal` - Log errors to journalctl
- **DynamicUser**: Creates ephemeral user per execution (security)

### Timer Configuration
- **OnBootSec**: `15` - Start 15 seconds after boot
- **OnUnitActiveSec**: `15` - Trigger 15 seconds after previous execution completes
- **AccuracySec**: `1s` - Prevent timer drift (default is 1 minute)

## Healthchecks.io Configuration

**Recommended settings** on healthchecks.io:
- **Period**: 1 minute (4 pings expected per period)
- **Grace time**: 1 minute (allow one missed interval before alerting)
- **Type**: Simple (just success/failure, no logs needed)

This gives you ~75 seconds before alert (1 min period + 1 min grace - 15s last ping).

## Comparison with Agent Healthcheck

| Feature | Host Monitor | Gardener Agent |
|---------|--------------|----------------|
| **Purpose** | Verify host is alive | Verify agent execution succeeds |
| **Frequency** | Every 15 seconds | Every 10 minutes |
| **Implementation** | systemd timer + curl | Bash loop with healthcheck() |
| **Healthcheck URL** | Configured at install time | Different slug (in .env.agent) |
| **Failure indicates** | Host down or network issue | Agent crash or MCP failure |

## Lessons Learned

- **Systemd timers**: Perfect for frequent, reliable pings with built-in logging
- **KISS principle**: 3 files (~100 lines total) for complete monitoring solution
- **YAGNI principle**: No env files, no config, no retry logic needed
- **Rate limits**: 15-second interval (4/min) balances responsiveness with healthchecks.io limits
- **Security**: DynamicUser provides isolation without creating dedicated system users

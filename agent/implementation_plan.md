# Raspberry Pi Agent Deployment Plan

## Overview
Deploy Claude Code agent to run headless on Raspberry Pi as isolated `gardener` user, executing every 20 minutes with health monitoring and automatic gatekeeper reset.

## Architecture
- **Admin user**: Owns repo, runs install script
- **MCP user**: Runs plant-tools MCP server (already deployed)
- **Gardener user**: Runs Claude Code agent, isolated with zero repo access, only HTTP to localhost MCP
- **Systemd timer**: Triggers agent runs 20 minutes after previous run completes (OnUnitInactiveSec)
- **Gatekeeper reset**: ExecStopPost calls admin endpoint to reset cycle flag after each run

## Components

### Installation Script (`agent/install-agent.sh`)
Idempotent script run by admin with sudo:
- Create gardener system user (nologin shell)
- Install Claude Code CLI as gardener user
- Copy configs to `/home/gardener/`: prompt.txt, run-agent.sh, .mcp.json, settings.json
- Install systemd service file (Type=oneshot) and timer file
- Create log directory
- Set permissions

### Agent Runner (`deploy/run-agent.sh`)
Single-execution script triggered by systemd timer:
- Flock-based locking (report violations to healthchecks.io)
- Single run: healthcheck start → execute claude → healthcheck success/fail → exit
- Execute: `claude --output-format json --mcp-config ~/.mcp.json -p "$(cat ~/prompt.txt)"`
- Log to timestamped files
- Exit with proper status code for systemd tracking

### Systemd Timer (`deploy/gardener-agent.timer`)
Timer unit that schedules agent runs:
- **OnBootSec=1min**: First run 1 minute after boot
- **OnUnitInactiveSec=20min**: Subsequent runs 20 minutes after previous run completes
- Guarantees fixed gap between runs regardless of execution time

### Configuration Files
- **prompt.txt**: Agent prompt for each execution
- **.mcp.json**: MCP server config (plant-tools HTTP endpoint)
- **.env.agent.example**: Template for ANTHROPIC_API_KEY and HEALTHCHECK_URL
- **settings.json**: Claude Code permissions and output style
- **gardener-agent.service**: Systemd service definition

## Deployment Steps
1. Create `.env.agent` from template with API key and healthcheck URL
2. Run: `sudo bash agent/install-agent.sh`
3. Test manually: `sudo -u gardener /home/gardener/run-agent.sh` (will run once and exit)
4. Enable timer: `sudo systemctl enable --now gardener-agent.timer`
5. Monitor: `journalctl -u gardener-agent -f` or healthchecks.io
6. Check timer: `systemctl status gardener-agent.timer` and `systemctl list-timers`

## Key Decisions
- Files copied (not symlinked) - gardener has zero repo access
- ANTHROPIC_API_KEY for authentication (no OAuth token expiry)
- **Timer-based scheduling**: OnUnitInactiveSec ensures 20-minute gap after run completes
- **Oneshot service**: Runs once per timer trigger, exits with status code
- **Automatic gatekeeper reset**: ExecStopPost calls admin endpoint after each run (success or failure)
- **Admin endpoint**: POST /admin/reset-cycle resets gatekeeper flag (localhost-only, no auth)
- Health monitoring before and after each execution
- No session continuity across runs (fresh Claude instance each time)

## Gatekeeper Reset Mechanism

The plant care system uses a gatekeeper pattern to ensure the agent assesses plant status before taking actions. The gatekeeper flag must be reset between agent runs.

### Problem
The MCP server runs as a long-lived HTTP service, but the gatekeeper flag (`current_cycle_status["written"]`) was never resetting between agent invocations. After the first run, `write_plant_status()` would reject all subsequent attempts with "Status already written for this cycle", blocking all action tools.

### Solution
Systemd timer architecture with automatic reset:

1. **Timer triggers service**: gardener-agent.timer waits 20 minutes after previous run completes
2. **Service runs agent once**: gardener-agent.service (Type=oneshot) executes run-agent.sh
3. **Agent runs and exits**: Script exits with status code (0=success, non-zero=failure)
4. **ExecStopPost always runs**: Calls `curl -X POST http://localhost:8000/admin/reset-cycle`
5. **Gatekeeper resets**: Admin endpoint calls `reset_cycle()` in shared_state.py
6. **Timer schedules next run**: Waits 20 minutes after service becomes inactive

### Benefits
- **Guaranteed reset**: ExecStopPost runs even if agent crashes
- **No manual intervention**: Fully automatic recovery from failures
- **Simple implementation**: Single HTTP endpoint, no complex state management
- **Idempotent**: Calling reset multiple times is safe
- **Observable**: Timer status visible via `systemctl list-timers`

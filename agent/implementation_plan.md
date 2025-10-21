# Raspberry Pi Agent Deployment Plan

## Overview
Deploy Claude Code agent to run headless on Raspberry Pi as isolated `gardener` user, executing every 10 minutes with health monitoring.

## Architecture
- **Admin user**: Owns repo, runs install script
- **MCP user**: Runs plant-tools MCP server (already deployed)
- **Gardener user**: Runs Claude Code agent, isolated with zero repo access, only HTTP to localhost MCP

## Components

### Installation Script (`deploy/install.sh`)
Idempotent script run by admin with sudo:
- Create gardener system user (nologin shell)
- Install Claude Code CLI as gardener user
- Copy configs to `/home/gardener/`: prompt.txt, run-agent.sh, .mcp.json, settings.local
- Install systemd service file
- Create log directory
- Set permissions

### Agent Runner (`deploy/run-agent.sh`)
Continuous loop script copied to gardener home:
- Flock-based locking (report violations to healthchecks.io)
- Infinite loop: healthcheck start → execute claude → healthcheck success/fail → sleep 600s
- Execute: `claude --continue --output-format json -p "$(cat ~/prompt.txt)"`
- Log to timestamped files

### Configuration Files
- **prompt.txt**: Agent prompt for each execution
- **.mcp.json**: MCP server config (plant-tools HTTP endpoint)
- **.env.agent.example**: Template for ANTHROPIC_API_KEY and HEALTHCHECK_URL
- **settings.local**: Claude Code permissions and output style
- **gardener-agent.service**: Systemd service definition

## Deployment Steps
1. Create `.env.agent` from template with API key and healthcheck URL
2. Run: `sudo bash agent/deploy/install.sh`
3. Test manually: `sudo -u gardener /home/gardener/run-agent.sh` (Ctrl+C after one cycle)
4. Enable service: `sudo systemctl enable --now gardener-agent`
5. Monitor: `journalctl -u gardener-agent -f` or healthchecks.io

## Key Decisions
- Files copied (not symlinked) - gardener has zero repo access
- ANTHROPIC_API_KEY for authentication (no OAuth token expiry)
- Session continuity via --continue flag
- Fixed 10-minute interval between runs (sleep 600s after completion)
- Health monitoring before and after each execution

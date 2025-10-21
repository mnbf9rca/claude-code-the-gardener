# Gardener Agent Deployment

Automated deployment for Claude Code agent running on Raspberry Pi.

## Prerequisites

- Raspberry Pi with Debian 13 (Trixie)
- Repository cloned by admin user
- MCP plant-tools server running (http://localhost:8000/mcp)
- Anthropic API key
- Healthchecks.io account (optional but recommended)

## Quick Start

### 1. Configure Environment (Required)

Create `.env.agent` from the example template **before running installation**:

```bash
cd agent/deploy
cp .env.agent.example .env.agent
nano .env.agent  # Edit with your API key and healthcheck URL
```

**Note:** The installation script will fail if `.env.agent` is missing.

### 2. Run Installation Script

```bash
sudo bash agent/deploy/install.sh
```

The script validates all required files exist, then:
- Create `gardener` system user
- Install Claude Code CLI
- Copy configuration files to `/home/gardener/`
- Install systemd service

### 3. Test Manually

Before enabling the service, test one execution cycle:

```bash
sudo -u gardener /home/gardener/run-agent.sh
```

Watch the output. Press Ctrl+C after observing one complete cycle (this may take several minutes).

### 4. Enable Service

```bash
sudo systemctl enable --now gardener-agent
```

### 5. Monitor

**View live logs:**
```bash
journalctl -u gardener-agent -f
```

**Check service status:**
```bash
sudo systemctl status gardener-agent
```

**View log files:**
```bash
sudo ls -lh /home/gardener/logs/
sudo ls -t /home/gardener/logs/agent_*.log | head -1 | xargs tail -f  # Follow latest
sudo cat /home/gardener/logs/agent_20250121_143000.log  # View specific log
```

**Note:** Each execution creates a new timestamped log file. At ~200KB per run and 144 runs/day, it takes ~36 days to accumulate 1GB of logs. If the log directory exceeds 1GB, the agent will signal failure to healthchecks.io (but continue executing)

**Monitor via Healthchecks.io:**
Visit your healthchecks.io dashboard to see execution history and alerts.

## Updating Configuration

To update the agent prompt, MCP configuration, or other settings:

1. Edit files in the repository (`agent/deploy/`)
2. Re-run the installation script: `sudo bash agent/deploy/install.sh`
3. Restart the service: `sudo systemctl restart gardener-agent`

**Note:** The installation script will NOT overwrite an existing `.env.agent` by default to prevent accidentally replacing your API key. To force update all files including `.env.agent`:

```bash
sudo bash agent/deploy/install.sh --force
```

This will backup the existing `.env.agent` to `.env.agent.bak` before overwriting.

## Architecture

- **gardener** user: Runs Claude Code agent, isolated with no repo access
- **Working directory**: `/home/gardener/`
- **Session data**: `/home/gardener/.claude/`
- **Execution interval**: 10 minutes between runs
- **Health monitoring**: Pings healthchecks.io before/after each execution

## Troubleshooting

**Service won't start:**
- Check `.env.agent` exists and contains valid `ANTHROPIC_API_KEY`
- Verify MCP server is running: `curl http://localhost:8000/mcp`
- View logs: `journalctl -u gardener-agent -n 50`

**Lock file errors:**
- Another instance may be running: `ps aux | grep run-agent.sh`
- Remove stale lock: `sudo rm /home/gardener/.gardener-agent.lock`

**Claude authentication errors:**
- Ensure `ANTHROPIC_API_KEY` is set correctly in `.env.agent`
- Test as gardener user: `sudo -u gardener -i` then check environment

**Execution failures:**
- Check individual log files in `/home/gardener/logs/`
- Verify prompt.txt exists: `sudo cat /home/gardener/prompt.txt`
- Test Claude manually: `sudo -u gardener claude --version`

**Log directory exceeds 1GB:**
- Agent signals failure to healthchecks.io but continues executing
- Clean up old logs when convenient: `sudo rm /home/gardener/logs/agent_2025*.log` (adjust pattern)
- Or delete all logs: `sudo rm -rf /home/gardener/logs/* && sudo mkdir -p /home/gardener/logs`

## Security

The gardener user:
- Has no shell access (nologin)
- Cannot access the repository
- Cannot modify its own configuration files (all configs are root-owned and read-only)
- Cannot edit its own prompt or MCP server list
- Can only interact with the plant via MCP HTTP API
- Can only write to its own logs and Claude session data
- Runs with systemd security hardening (NoNewPrivileges, PrivateTmp)

## Uninstalling

```bash
# Stop and disable service
sudo systemctl stop gardener-agent
sudo systemctl disable gardener-agent

# Remove service file
sudo rm /etc/systemd/system/gardener-agent.service
sudo systemctl daemon-reload

# Optional: Remove gardener user and data
sudo userdel -r gardener
```

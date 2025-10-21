# MCP Server Deployment Plan

## Prerequisites
- Raspberry Pi running Debian 13 (Trixie)
- Repository cloned to Raspberry Pi
- `.env` file created from `app/.env.example` with proper configuration
- Internet connection for downloading dependencies

## Deployment Steps

### 1. Prepare Environment
```bash
cd /path/to/claude-code-the-gardener
cp app/.env.example app/.env
# Edit app/.env with appropriate values for mcpserver paths
```

### 2. Run Installation Script
```bash
sudo bash app/deploy/install-mcp-server.sh
```

The script will:
- Create `mcpserver` system user
- Install `uv` package manager for mcpserver user
- Copy app directory to `/home/mcpserver/plant-care-app/`
- Create deployment info file with git commit hash
- Install Python dependencies via `uv sync`
- Create data and photos directories
- Copy `.env` configuration
- Install and configure systemd service

### 3. Enable and Start Service
```bash
sudo systemctl enable plant-care-mcp.service
sudo systemctl start plant-care-mcp.service
```

### 4. Verify Deployment
```bash
# Check service status
sudo systemctl status plant-care-mcp.service

# View logs
journalctl -u plant-care-mcp.service -f

# Check running version
cat /home/mcpserver/plant-care-app/.deployment-info

# Test HTTP endpoint
curl http://localhost:8000/mcp
```

## Update Workflow

To deploy code changes:
```bash
cd /path/to/claude-code-the-gardener
git pull origin main
sudo bash app/deploy/install-mcp-server.sh
# Script automatically restarts service with new code
```

## Service Management

```bash
# Start service
sudo systemctl start plant-care-mcp.service

# Stop service
sudo systemctl stop plant-care-mcp.service

# Restart service
sudo systemctl restart plant-care-mcp.service

# View status
sudo systemctl status plant-care-mcp.service

# View logs (real-time)
journalctl -u plant-care-mcp.service -f

# View recent logs
journalctl -u plant-care-mcp.service -n 100

# View error logs only
journalctl -u plant-care-mcp.service -p err
```

## Directory Structure

```
/home/mcpserver/
├── .env                          # Environment configuration
├── .local/bin/uv                 # UV package manager
├── plant-care-app/               # Copied from repo app/
│   ├── .deployment-info          # Git commit, timestamp, deployed-by
│   ├── server.py                 # MCP server
│   ├── run_http.py               # HTTP server entry point
│   └── ...
├── data/                         # JSONL state files
│   ├── thoughts.jsonl
│   ├── action_log.jsonl
│   ├── water_pump_usage.jsonl
│   └── ...
└── photos/                       # Camera captures
    └── YYYY-MM-DD_HH-MM-SS_UTC.jpg
```

## Configuration Notes

Key `.env` settings for mcpserver:
- `MCP_HOST=0.0.0.0` - Listen on all interfaces
- `MCP_PORT=8000` - HTTP port
- `CAMERA_SAVE_PATH=/home/mcpserver/photos` - Photo storage
- Data files auto-created in `/home/mcpserver/data/`

## Security

- Service runs as dedicated `mcpserver` user (no login shell)
- No special privileges required
- Isolated from main user and gardener agent
- Read-only access to deployed code
- Data written to mcpserver home directory only

## Troubleshooting

### Service fails to start
```bash
journalctl -u plant-care-mcp.service -n 50
```

### Check deployment version
```bash
cat /home/mcpserver/plant-care-app/.deployment-info
```

### Permission issues
```bash
ls -la /home/mcpserver/
sudo chown -R mcpserver:mcpserver /home/mcpserver/
```

### Camera not working
```bash
# Check camera device as mcpserver user
sudo -u mcpserver ls -la /dev/video*
# May need to add mcpserver to video group
sudo usermod -a -G video mcpserver
sudo systemctl restart plant-care-mcp.service
```

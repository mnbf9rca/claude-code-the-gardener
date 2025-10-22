# Plant Care MCP Server

An autonomous plant care system powered by Claude AI using the Model Context Protocol (MCP). This system monitors and maintains plant health through automated watering, lighting, and environmental monitoring.

## Overview

Claude AI runs every 10 minutes (via cron) to:

- Monitor soil moisture levels
- Control a water pump (with safety limits)
- Manage grow lights via Home Assistant
- Capture photos of the plant
- Log thoughts and reasoning
- Track all actions

## Architecture

- **MCP Server**: FastMCP-based server providing tools for plant care
- **ESP32**: Handles sensors and pump (moisture sensor, water pump relay)
- **Raspberry Pi**: Runs the MCP server, camera, and Home Assistant integration
- **Home Assistant**: Controls the grow light via Meross smart plug

## Tools Available

### Monitoring Tools

- `moisture_sensor.read()` - Read soil moisture sensor value
- `camera.capture()` - Take a photo of the plant
- `thinking.get_recent()` / `search()` - Review past reasoning
- `action_log.get_recent()` / `search()` - Review past actions

### Action Tools

- `water_pump.dispense(ml)` - Dispense 10-100ml of water (500ml/24h limit)
- `light.turn_on(minutes)` - Turn on grow light for 30-120 minutes
- `thinking.log_thought()` - Record observations and reasoning
- `action_log.log_action()` - Record actions taken

### Status Tool

- `plant_status.write_status()` - **Required first call** each cycle - sets plan and state

## Development Setup

### Prerequisites

- Python 3.13+
- uv (Python package manager)
- OpenCV (for camera)
- Home Assistant (for light control)

### Installation

```bash
# Clone the repository
cd app

# Install dependencies
uv sync --dev

# Copy environment template
cp .env.example .env

# Edit .env with your configuration
# - DATA_DIR and CAMERA_SAVE_PATH (REQUIRED - must be outside app directory)
# - Home Assistant URL and token
# - Camera settings
# - MCP server host/port
```

### Running Locally


#### Option 1: HTTP Server (for remote access)

```bash
# Start the HTTP server
uv run python run_http.py

# Server will be available at:
# http://localhost:8000/mcp
```

#### Option 2: STDIO (for local MCP inspector)

```bash
# Run MCP inspector (opens browser)
uv run fastmcp dev server.py
```

#### Option 3: VS Code Debug

Open the project in VS Code and use the debug configurations:

- **Run HTTP Server** - Start the HTTP server with debugging
- **Run MCP Dev Inspector** - Start the browser-based inspector
- **Run MCP Server (stdio)** - Start stdio transport for testing
- **Run All Tests** - Run the test suite with debugging

### Running Tests

```bash
# Run all tests
uv run pytest -v

# Run specific test file
uv run pytest test_water_pump.py -v

# Run tests with coverage
uv run pytest --cov=tools -v
```

## Deployment to Raspberry Pi

### 1. Install Dependencies on Raspberry Pi

```bash
# Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# Clone repository
cd ~
git clone <your-repo-url> claude-code-the-gardener
cd claude-code-the-gardener/app

# Install dependencies
uv sync
```

### 2. Configure Environment

```bash
# Copy environment template
cp .env.example .env

# Edit configuration
nano .env
```

Required settings:

- **`DATA_DIR`** - JSONL history storage (MUST be outside app directory, e.g., `../data`)
- **`CAMERA_SAVE_PATH`** - Photo storage (MUST be outside app directory, e.g., `../photos`)
- `HOME_ASSISTANT_URL` - Your Home Assistant URL
- `HOME_ASSISTANT_TOKEN` - Long-lived access token
- `LIGHT_ENTITY_ID` - Your smart plug entity ID
- `CAMERA_DEVICE_INDEX` - USB camera index (usually 0)
- `MCP_HOST=0.0.0.0` - Bind to all interfaces
- `MCP_PORT=8000` - HTTP port

**⚠️ CRITICAL**: `DATA_DIR` and `CAMERA_SAVE_PATH` must be outside the application directory. The installation script deletes and recreates the app directory on updates, which would delete all historical data if stored inside. Use relative paths like `../data` and `../photos` to store data outside the app folder.

### 3. Set Up Systemd Service

```bash
# Copy service file
sudo cp ../plant-care-mcp.service /etc/systemd/system/

# Edit service file if your paths differ
sudo nano /etc/systemd/system/plant-care-mcp.service

# Reload systemd
sudo systemctl daemon-reload

# Enable service to start on boot
sudo systemctl enable plant-care-mcp.service

# Start the service
sudo systemctl start plant-care-mcp.service

# Check status
sudo systemctl status plant-care-mcp.service
```

### 4. View Logs

```bash
# Follow live logs
sudo journalctl -u plant-care-mcp.service -f

# View recent logs
sudo journalctl -u plant-care-mcp.service -n 100
```

### 5. Set Up Cron Job (for Claude to run every 10 minutes)

```bash
# Edit crontab
crontab -e

# Add this line to run Claude every 10 minutes:
*/10 * * * * /path/to/claude-cli --mcp http://localhost:8000/mcp
```

## Logging

The application uses Python's built-in logging module with centralized configuration:

### Log Levels

Control logging verbosity via the `LOG_LEVEL` environment variable:

- **DEBUG**: Detailed diagnostic information (state changes, reconciliation steps, background tasks)
- **INFO**: Informational messages (server startup, successful operations, state changes)
- **WARNING**: Warning messages (failed operations, fallback modes, retries)
- **ERROR**: Error messages (critical failures, exceptions)
- **CRITICAL**: Critical failures (not currently used)

### Configuration

```bash
# In .env file
LOG_LEVEL=INFO  # Default for production
LOG_LEVEL=DEBUG # Use for development/debugging
```

### Systemd Integration

When running via systemd, logs are automatically sent to journald:

```bash
# View real-time logs
sudo journalctl -u plant-care-mcp.service -f

# View logs with specific level
sudo journalctl -u plant-care-mcp.service -p warning

# View logs from last hour
sudo journalctl -u plant-care-mcp.service --since "1 hour ago"
```

### Log Format

```shell
YYYY-MM-DD HH:MM:SS - module.name - LEVEL - Message
```

Example:

```shell
2025-10-19 09:00:00 - tools.light - INFO - Light turned off successfully at scheduled time
2025-10-19 09:00:01 - tools.water_pump - WARNING - Approaching daily water limit (450/500ml used)
```

## Environment Variables

check `.env.example` for all required environment variables.

## Project Structure

```shell
app/
 server.py                 # Main MCP server setup
 run_http.py              # HTTP server runner
 tools/                   # MCP tool implementations
    plant_status.py     # Gatekeeper tool (required first)
    moisture_sensor.py  # Soil moisture reading
    water_pump.py       # Water dispensing with limits
    light.py            # Grow light control
    camera.py           # Photo capture
    thinking.py         # Thought logging
    action_log.py       # Action logging
 utils/                   # Shared utilities
    jsonl_history.py    # JSONL state management
 data/                    # Runtime data (auto-created)
    *.jsonl             # History logs
    *.json              # State files
 photos/                  # Captured images (auto-created)
 test_*.py               # Test files
```

## Hardware Setup

### ESP32 (M5 CoreS3 SE)

- Capacitive soil moisture sensor
- 2-channel relay (for pump)
- Peristaltic pump (5-6V DC)

### Raspberry Pi

- USB webcam (Logitech C930e or similar)
- Network connection to Home Assistant

### Smart Home

- Meross smart plug (for grow light)
- Home Assistant instance

## Safety Features

- **Water limit**: Maximum 500ml per 24-hour rolling window
- **Light timing**: 30-120 min sessions, 30 min cooldown between
- **ESP32 failsafe**: Hardware timeout on pump activation
- **State persistence**: All actions logged to JSONL files
- **Auto-restart**: Systemd ensures service recovery

## Testing

The project includes 146 tests covering:

- Unit tests for all tools
- Integration tests for external services
- Time-based testing (freezegun)
- Mock hardware for offline testing

## Development Notes

- **Phase 1-3**: Core tools implemented with comprehensive testing
- **Phase 4**: HTTP deployment (current)
- **Future**: Real ESP32 integration (currently using mocks)

## License

See parent repository for license information.

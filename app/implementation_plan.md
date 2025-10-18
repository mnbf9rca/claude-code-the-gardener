# Plant Care MCP Implementation Plan

## Current Status
- **Phase 1: COMPLETED ✅** - Core MCP setup with basic tools
- **Phase 2: COMPLETED ✅** - Action tools with state persistence and integrations
- 91 tests passing
- Ready for Phase 3

## Phase 1: Core MCP Setup & Basic Tools (COMPLETED ✅)
- [x] Install FastMCP and dependencies in pyproject.toml
- [x] Create basic FastMCP server structure in app/server.py
- [x] Create tools directory structure
- [x] Implement plant_status tool (gatekeeper)
- [x] Implement moisture_sensor tool with mock data
- [x] Create test suite (21 tests: 6 unit for plant_status, 8 unit for moisture_sensor, 7 integration)
- [x] Address all code review feedback
- [x] Fix type consistency using Pydantic models

## Phase 2: Action Tools (COMPLETED ✅)
### Core Implementation
- [x] Water Pump (`app/tools/water_pump.py`)
   - [x] Daily usage limit enforcement (500ml/24hr)
   - [x] JSONL state persistence for append-only history
   - [x] Usage query and tracking
   - [x] 10 comprehensive tests
- [x] Light Control (`app/tools/light.py`)
   - [x] Home Assistant HTTP API integration (Meross smart plug)
   - [x] Timing constraints (30-120 min on, 30 min cooldown)
   - [x] Automatic scheduling with background tasks
   - [x] Startup state reconciliation
   - [x] Dual persistence (JSON for state, JSONL for history)
   - [x] HTTP client cleanup on shutdown
   - [x] 40 comprehensive tests (unit + integration + scheduling)
- [x] Camera (`app/tools/camera.py`)
   - [x] Real USB webcam capture (OpenCV)
   - [x] Cross-platform support (Mac/Raspberry Pi)
   - [x] Environment-based configuration
   - [x] JSONL usage logging
   - [x] Thread-safe camera access
   - [x] 16 comprehensive tests

### Infrastructure & Quality
- [x] JSONL standardization for all history/logs
- [x] Resource cleanup (HTTP clients, camera)
- [x] VS Code debug configurations
- [x] Environment variable configuration (.env.example)
- [x] Test fixtures and integration tests
- [x] Time-based testing with freezegun

## Phase 3: Thinking & Logging (Third PR)
1. **Implement state management tools**
   - `app/tools/thinking.py` - Store thoughts/plans
   - `app/tools/action_log.py` - Track actions
   - In-memory storage with list/dict structures

2. **Add query capabilities**
   - Implement `get_recent()`, `search()` methods
   - Simple substring matching

## Phase 4: HTTP Deployment (Fourth PR)
1. **Add HTTP server capability**
   - Use FastMCP's built-in HTTP server
   - Create `app/run_http.py` for deployment
   - Basic CORS configuration

2. **Create deployment configuration**
   - `fastmcp.json` for server configuration
   - systemd service file for Raspberry Pi

## Key Design Decisions
- No database initially - in-memory dictionaries
- Mock hardware - realistic fake data
- Single server with multiple tools
- No authentication initially
- Simple flat file structure
- Pydantic models for type safety

## Lessons Learned

### Phase 1
- FastMCP supports Pydantic models as tool parameters
- Test isolation is crucial - use pytest fixtures
- Separate unit tests from integration tests for clarity
- Mock data helps test without hardware dependencies
- Type consistency improves code reliability
- Code review feedback is valuable for improvement

### Phase 2
- JSONL append-only logs work well for time-series data
- Home Assistant HTTP API is reliable for IoT control
- Background asyncio tasks need proper lifecycle management
- Resource cleanup (HTTP clients, cameras) prevents leaks
- Environment variables provide good configuration flexibility
- OpenCV works consistently across Mac and Raspberry Pi
- Startup reconciliation prevents state drift

## How to Run

### Development Server
```bash
# Install dependencies
uv sync --dev

# Run MCP inspector (opens browser)
uv run fastmcp dev server.py

# Run server with stdio transport
uv run fastmcp run server:mcp --transport stdio
```

### Running Tests
```bash
# Run all tests
uv run pytest test_*.py -v

# Run specific test file
uv run pytest test_plant_status.py -v

# Run manual debugging test
uv run python manual_debug.py
```

## Ready for Phase 3

- All action tools implemented and tested (91 tests)
- State persistence standardized on JSONL
- Home Assistant integration working
- Real hardware integration (camera) validated
- Resource management patterns established
- Clear patterns for adding new tools

## Technical Notes for Next Phase

### What Works

- Water pump: Full JSONL history, daily limits enforced
- Light: HA integration, scheduling, state reconciliation
- Camera: Real USB capture, cross-platform tested
- All tools: Proper resource cleanup and error handling

### Configuration Required

- `.env` file needed with Home Assistant credentials for light control
- Camera requires USB webcam (auto-detects device_index 0)
- All state files stored in `app/data/` directory (auto-created)

### Known Limitations

- Water_pump, moisture_sensor uses mock ESP32 (no real hardware yet) - need to be replaced with real HTTP calls to esp32 device once built
- Light requires Home Assistant running and accessible
- Camera requires OpenCV and USB webcam hardware
- No authentication on MCP server yet

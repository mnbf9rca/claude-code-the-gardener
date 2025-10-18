# Plant Care MCP Implementation Plan

## Current Status
- **Phase 1: COMPLETED ✅** - Core MCP setup with basic tools
- **Phase 2: COMPLETED ✅** - Action tools with state persistence and integrations
- **Phase 3: COMPLETED ✅** - Thinking & logging tools + JSONL refactoring
- 146 tests passing (55 new tests in Phase 3)
- Ready for Phase 4

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

## Phase 3: Thinking & Logging (COMPLETED ✅)
### Core Implementation
- [x] Thinking Tool (`app/tools/thinking.py`)
   - [x] `log_thought()` with structured reasoning (observation, hypothesis, candidate_actions, reasoning, uncertainties, tags)
   - [x] `get_recent(n, offset)` with pagination support
   - [x] `get_range(start_time, end_time)` for time-based queries
   - [x] `search(keyword, hours)` for keyword searching
   - [x] JSONL persistence with 1000-entry memory cache
   - [x] 14 comprehensive tests
- [x] Action Log Tool (`app/tools/action_log.py`)
   - [x] `log_action(type, details)` with type validation (water|light|observe|alert)
   - [x] `get_recent(n, offset)` with pagination support
   - [x] `search(keyword, hours)` for keyword searching
   - [x] JSONL persistence with 1000-entry memory cache
   - [x] 17 comprehensive tests

### Infrastructure
- [x] Updated server.py to register new tools
- [x] Updated tool_descriptions.md with detailed API documentation
- [x] Memory-efficient deque-based storage
- [x] Auto-loading state from disk on first use

### JSONL Refactoring (Completed)
- [x] Created `utils/jsonl_history.py` - centralized JSONL state management utility
- [x] 24 comprehensive tests for JsonlHistory utility
- [x] Refactored all 5 modules to use JsonlHistory:
   - thinking.py (-42% code reduction)
   - action_log.py (-51% code reduction)
   - water_pump.py (-51% code reduction)
   - light.py (removed 100+ lines of manual JSONL code)
   - camera.py (simplified audit logging)
- [x] Fixed lazy loading bug in get_by_time_window()
- [x] All 146 tests passing
- [x] ~300 lines of duplicated code eliminated

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

### Phase 3
- In-memory deques with JSONL persistence scale well (1000 entries in memory)
- Pagination support (offset parameter) enables efficient browsing of large histories
- Simple substring search is sufficient for a hobby project
- Pydantic Literal types provide clean enum validation
- Consistent patterns across tools make testing straightforward
- freezegun library is invaluable for time-based testing
- **DRY refactoring**: Following "Rule of Three" - consolidating after 3+ duplications pays off
- Centralized utilities (JsonlHistory) eliminate bugs across all modules simultaneously
- Missing ensure_loaded() calls are easy to miss - having one implementation prevents this

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

## Ready for Phase 4

- All core tools implemented and tested (146 tests)
- State persistence fully consolidated via JsonlHistory utility
- JSONL used consistently across all 5 stateful modules
- Home Assistant integration working
- Real hardware integration (camera) validated
- Resource management patterns established
- Thinking and action logging ready for Claude to use
- Clean, DRY codebase with minimal duplication
- New stateful tools can use JsonlHistory out of the box

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

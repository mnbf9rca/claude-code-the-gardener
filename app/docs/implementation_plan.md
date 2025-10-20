# Plant Care MCP Implementation Plan

## Current Status
- **Phase 1: COMPLETED ✅** - Core MCP setup with basic tools
- **Phase 2: COMPLETED ✅** - Action tools with state persistence and integrations
- **Phase 3: COMPLETED ✅** - Thinking & logging tools + JSONL refactoring
- **Phase 4: COMPLETED ✅** - HTTP deployment with systemd service
- **Phase 5: COMPLETED ✅** - UTC timestamps & HTTP image retrieval
- **153 tests passing** (all timezone issues resolved)
- Ready for production deployment on Raspberry Pi

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

## Phase 4: HTTP Deployment (COMPLETED ✅)
### HTTP Server
- [x] Created `app/run_http.py` - HTTP server runner with environment configuration
- [x] Environment variables for host/port configuration (MCP_HOST, MCP_PORT)
- [x] Streamable HTTP transport (FastMCP's recommended transport)
- [x] Tested locally - server starts and responds correctly

### Deployment Infrastructure
- [x] Created `plant-care-mcp.service` - systemd service file for Raspberry Pi
  - [x] Auto-restart on failure
  - [x] Runs as non-root user (pi)
  - [x] Environment file support
  - [x] Journal logging
- [x] Updated `.env.example` with MCP server configuration
- [x] Created comprehensive README.md with:
  - [x] Development setup instructions
  - [x] Local testing guide
  - [x] Raspberry Pi deployment steps
  - [x] Systemd service setup
  - [x] Environment variable documentation

### Development Tools
- [x] Created `.vscode/launch.json` with 4 debug configurations:
  - [x] Run HTTP Server
  - [x] Run MCP Server (stdio)
  - [x] Run MCP Dev Inspector
  - [x] Run All Tests

## Phase 5: UTC Timestamps & HTTP Image Retrieval (COMPLETED ✅)

### Core Implementation
- [x] UTC Time Tool (`app/tools/utcnow.py`)
  - [x] `get_current_time()` returns UTC timestamp
  - [x] Allows Claude to query current date/time for temporal reasoning
  - [x] 3 comprehensive tests
- [x] HTTP Static File Serving
  - [x] Added FastAPI static files mount in `run_http.py`
  - [x] Photos served via `/photos/{filename}` endpoint
  - [x] Auto-creates photos directory on startup
- [x] Timestamp Consistency Audit
  - [x] All tools now use `datetime.now(timezone.utc)` instead of `datetime.now()`
  - [x] Fixed `camera.py` timestamp inconsistency (single timestamp for filename, log, and response)
  - [x] Updated `utils/jsonl_history.py` for timezone-aware comparisons
  - [x] Camera tool returns HTTP URLs instead of file paths
- [x] Environment Configuration
  - [x] Added `MCP_PUBLIC_HOST` to `.env.example` for photo URL construction
  - [x] Updated all 7 tool modules with timezone imports
- [x] Testing
  - [x] Created `test_utcnow.py` with 3 tests
  - [x] Updated camera tests to handle HTTP URLs
  - [x] Fixed all test fixtures to use timezone-aware datetimes
  - [x] **All 153 tests passing**

### Lessons Learned
- **UTC everywhere**: Using `datetime.now(timezone.utc)` eliminates timezone bugs and DST issues
- **Timestamp consistency**: Generating timestamp once per operation prevents subtle mismatches
- **Static file serving**: FastAPI's built-in static files feature is perfect for serving photos (no nginx needed)
- **Test fixture updates**: When changing time handling, test fixtures need corresponding updates
- **KISS for hobby projects**: HTTP photo URLs work fine; no need for CDN or complex image serving

## Phase 6: Notes Tools (COMPLETED ✅)

### Core Implementation
- [x] Notes Tool (`app/tools/notes.py`)
  - [x] `save_notes(content, mode)` with replace/append modes
  - [x] `fetch_notes()` to retrieve current note
  - [x] Timestamped audit archives in `app/data/notes_archive/`
  - [x] 13 comprehensive tests
- [x] Updated `server.py` to register notes tools

### Storage
- Current note: `app/data/notes.md` (plain file, not JSONL)
- Archives: `app/data/notes_archive/YYYY-MM-DD_HH-MM-SS_UTC.md`

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

### Phase 4
- FastMCP's built-in HTTP server eliminates need for external web servers (Nginx, Apache)
- Streamable HTTP is the recommended transport (better than legacy SSE)
- Environment variables (MCP_HOST, MCP_PORT) provide deployment flexibility
- Systemd services provide robust process management for production
- VS Code launch.json configurations dramatically improve developer experience
- KISS principle: ~100 lines of code/config for full production deployment
- No need for Docker, health checks, or metrics for a hobby project (YAGNI)
- Comprehensive README documentation is crucial for hobby projects that might sit idle

## How to Run

### Development Server
```bash
# Install dependencies
uv sync --dev

# Run HTTP server (for remote access)
uv run python run_http.py

# Run MCP inspector (opens browser)
uv run fastmcp dev server.py

# Run server with stdio transport
uv run fastmcp run server:mcp --transport stdio
```

### VS Code Debug Configurations
Use the Run & Debug panel (Cmd+Shift+D / Ctrl+Shift+D) to select:
- **Run HTTP Server** - Start HTTP server with debugging
- **Run MCP Dev Inspector** - Start browser-based inspector
- **Run MCP Server (stdio)** - Start stdio transport
- **Run All Tests** - Run pytest with debugging

### Running Tests
```bash
# Run all tests
uv run pytest -v

# Run specific test file
uv run pytest test_plant_status.py -v

# Run with coverage
uv run pytest --cov=tools -v
```

### Production Deployment
See [README.md](README.md) for complete Raspberry Pi deployment instructions with systemd.

## Ready for Production Deployment

- ✅ All core tools implemented and tested (146 tests)
- ✅ HTTP server with Streamable HTTP transport
- ✅ Systemd service for Raspberry Pi deployment
- ✅ Environment-based configuration (.env)
- ✅ Comprehensive documentation (README.md)
- ✅ VS Code debug configurations for development
- ✅ State persistence via JsonlHistory utility
- ✅ Home Assistant integration working
- ✅ Real hardware integration (camera) validated
- ✅ Resource management patterns established
- ✅ Clean, maintainable codebase following KISS and YAGNI

### Next Steps (Post-Deployment)
- Build ESP32 firmware for moisture sensor and water pump
- Replace mock sensor/pump tools with real HTTP calls to ESP32
- Deploy to Raspberry Pi and set up cron job for Claude
- Monitor Claude's plant care performance over time

## Production Deployment Notes

### What's Implemented and Working

- ✅ Water pump: Full JSONL history, daily limits enforced (mock ESP32)
- ✅ Light: Home Assistant integration, scheduling, state reconciliation
- ✅ Camera: Real USB capture, cross-platform tested (Mac/Raspberry Pi)
- ✅ Thinking & Action logs: JSONL persistence with efficient querying
- ✅ HTTP server: Streamable HTTP transport on configurable host/port
- ✅ All tools: Proper resource cleanup and error handling

### Configuration Required for Deployment

- `.env` file with configuration (see `.env.example`):
  - `MCP_HOST` and `MCP_PORT` for HTTP server
  - `HOME_ASSISTANT_URL` and `HOME_ASSISTANT_TOKEN` for light control
  - `LIGHT_ENTITY_ID` for smart plug entity
  - Camera settings (device index, resolution, quality)
- USB webcam connected to Raspberry Pi
- Home Assistant instance running and accessible
- All state files auto-created in `app/data/` directory
- Photo storage auto-created in `app/photos/` directory

### Known Limitations & Future Work

- ⚠️ **Mock hardware**: `moisture_sensor` and `water_pump` use mock ESP32 responses
  - Need to build ESP32 firmware
  - Replace mock calls with real HTTP calls to ESP32 device
- ⚠️ **No authentication**: MCP server has no auth (suitable for private network only)
- ⚠️ **Light dependency**: Requires Home Assistant running and accessible
- ⚠️ **Camera dependency**: Requires OpenCV and USB webcam hardware

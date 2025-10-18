# Plant Care MCP Implementation Plan

## Current Status
- Phase 1 COMPLETED ✅
- All core functionality working
- Tests passing

## Phase 1 Todo List (COMPLETED)
- [x] Install FastMCP and dependencies in pyproject.toml
- [x] Create basic FastMCP server structure in app/server.py
- [x] Create tools directory structure
- [x] Implement plant_status tool (gatekeeper)
- [x] Implement moisture_sensor tool with mock data
- [x] Create basic smoke tests
- [x] Test server locally to verify tools work

## Phase 1: Core MCP Setup & Basic Tools (First PR)
1. **Install FastMCP and dependencies** ✅
   - Added `fastmcp` and `pydantic` to pyproject.toml
   - Added test dependencies

2. **Create simple MCP server structure**
   - `app/server.py` - Main FastMCP server that composes all services
   - `app/tools/` directory for individual tool implementations

3. **Implement mandatory tools**
   - `app/tools/plant_status.py` - The gating tool (must be called first)
   - `app/tools/moisture_sensor.py` - Mock sensor reading
   - Use in-memory storage (dictionaries)

4. **Basic testing setup**
   - Create `app/test_server.py` with basic smoke tests
   - Test that tools are discoverable and callable

## Phase 2: Action Tools (Second PR)
1. **Implement action tools**
   - `app/tools/water_pump.py` - Track daily usage in memory
   - `app/tools/light.py` - Track on/off state and timing
   - `app/tools/camera.py` - Return placeholder URL

2. **Add simple validation**
   - Enforce 500ml/24hr water limit
   - Enforce light timing constraints
   - Use Pydantic models

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

## Implementation Notes
- Following KISS and YAGNI principles
- This is a hobby project, not enterprise
- Using PRs to checkpoint progress
- Focus on getting minimal working system first
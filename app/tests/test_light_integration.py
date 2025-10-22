"""
Real Integration Tests for Light Module with Home Assistant

These tests connect to a real Home Assistant instance and are kept MINIMAL.
Most functionality is tested via mocked tests in test_light.py (15 comprehensive tests).

These integration tests only verify:
1. Basic HA connectivity and API calls work
2. State synchronization between local and HA works
3. One timing constraint works with real HA

They are skipped if Home Assistant is not reachable.

To run these tests, ensure:
1. .env file exists with HOME_ASSISTANT_URL and HOME_ASSISTANT_TOKEN
2. Home Assistant is running and reachable
3. The entity LIGHT_ENTITY_ID exists in Home Assistant
"""
import pytest
import pytest_asyncio
import json
from dotenv import load_dotenv
from fastmcp import FastMCP
import tools.light as light_module
from tools.light import setup_light_tools, get_ha_entity_state
from utils.shared_state import reset_cycle, current_cycle_status

# Load environment variables
load_dotenv()


async def check_ha_available() -> bool:
    """Check if Home Assistant is reachable"""
    try:
        # Use get_ha_entity_state which properly handles HA requests
        config = light_module.get_ha_config()
        state = await light_module.get_ha_entity_state(config.entity_id)
        return state is not None
    except Exception:
        return False


@pytest_asyncio.fixture(scope="session")
async def ha_availability():
    """Check HA availability once per test session"""
    return await check_ha_available()


@pytest_asyncio.fixture(autouse=True)
async def setup_integration_state(ha_availability):
    """Reset light state before each integration test"""
    if not ha_availability:
        pytest.skip("Home Assistant is not available")

    # Reset cycle state
    reset_cycle()
    current_cycle_status["written"] = True

    # Note: NOT resetting HAConfig - reuse the same client across tests
    # Resetting causes "Server disconnected" errors with Home Assistant

    # Reset light state
    # Set last_off to None so each test starts fresh (bypasses cooldown check at light.py:56)
    light_module.light_state["status"] = "off"
    light_module.light_state["last_on"] = None
    light_module.light_state["last_off"] = None  # "Never used" - bypasses 30-min cooldown
    light_module.light_state["scheduled_off"] = None

    # Clear persisted state and history files
    light_module.STATE_FILE.unlink(missing_ok=True)
    light_module.light_history.file_path.unlink(missing_ok=True)
    light_module._state_loaded = False
    light_module.light_history.clear()
    light_module.light_history._loaded = False

    # HTTP client cleanup no longer needed (using async context managers)

    # Create MCP instance
    mcp = FastMCP("test-integration")
    setup_light_tools(mcp)

    # Ensure light is off before starting tests by calling HA directly
    config = light_module.get_ha_config()
    try:
        await light_module.call_ha_service("turn_off", config.entity_id)
    except Exception:
        pass  # Ignore errors if already off

    yield mcp

    # Cleanup - ensure light is off after tests by calling HA directly
    try:
        await light_module.call_ha_service("turn_off", config.entity_id)
    except Exception:
        pass

    # HTTP client cleanup no longer needed (using async context managers)


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.use_real_hardware
async def test_real_ha_entity_state_query(setup_integration_state):
    """Test querying real Home Assistant entity state"""
    config = light_module.get_ha_config()
    state = await get_ha_entity_state(config.entity_id)

    # Should return a valid state
    assert state is not None
    assert state in ["on", "off", "unavailable"]


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.use_real_hardware
async def test_real_turn_on_and_status(setup_integration_state):
    """Test turning on the real light and checking status"""
    import asyncio
    mcp = setup_integration_state
    turn_on_tool = mcp._tool_manager._tools["turn_on_light"]
    status_tool = mcp._tool_manager._tools["get_light_status"]

    # Turn on the light
    tool_result = await turn_on_tool.run(arguments={"minutes": 30})
    result = json.loads(tool_result.content[0].text)

    assert result["status"] == "on"
    assert result["duration_minutes"] == 30

    # Small delay to let Home Assistant process the state change
    await asyncio.sleep(0.5)

    # Verify with status check
    tool_result = await status_tool.run(arguments={})
    result = json.loads(tool_result.content[0].text)

    assert result["status"] == "on"
    assert result["last_on"] is not None


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.use_real_hardware
async def test_real_turn_off(setup_integration_state):
    """Test turning off the real light"""
    import asyncio
    mcp = setup_integration_state
    turn_on_tool = mcp._tool_manager._tools["turn_on_light"]
    turn_off_tool = mcp._tool_manager._tools["turn_off_light"]
    status_tool = mcp._tool_manager._tools["get_light_status"]

    # Turn on first
    await turn_on_tool.run(arguments={"minutes": 60})

    # Small delay for HA state propagation
    await asyncio.sleep(0.5)

    # Verify it's on
    tool_result = await status_tool.run(arguments={})
    result = json.loads(tool_result.content[0].text)
    assert result["status"] == "on"

    # Turn off
    tool_result = await turn_off_tool.run(arguments={})
    result = json.loads(tool_result.content[0].text)

    assert result["status"] == "off"
    assert "turned_off_at" in result

    # Small delay for HA state propagation
    await asyncio.sleep(0.5)

    # Verify with status check
    tool_result = await status_tool.run(arguments={})
    result = json.loads(tool_result.content[0].text)
    assert result["status"] == "off"


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.use_real_hardware
async def test_real_state_sync(setup_integration_state):
    """Test that status syncs with real Home Assistant state"""
    import asyncio
    mcp = setup_integration_state
    turn_on_tool = mcp._tool_manager._tools["turn_on_light"]
    status_tool = mcp._tool_manager._tools["get_light_status"]

    # Turn on the light
    await turn_on_tool.run(arguments={"minutes": 30})

    # Longer delay for HA state propagation (HA can be slow to update)
    await asyncio.sleep(2.0)

    # Clear local state to simulate desync
    light_module.light_state["status"] = "off"

    # Check status - should sync with HA
    tool_result = await status_tool.run(arguments={})
    result = json.loads(tool_result.content[0].text)

    # Should reflect actual HA state (on)
    assert result["status"] == "on"


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.use_real_hardware
async def test_real_timing_constraints(setup_integration_state):
    """Test that one timing constraint works with real HA (exhaustive testing in mocked tests)"""
    mcp = setup_integration_state
    turn_on_tool = mcp._tool_manager._tools["turn_on_light"]

    # Turn on the light
    await turn_on_tool.run(arguments={"minutes": 30})

    # Try to turn on again while it's already on - should fail
    with pytest.raises(ValueError, match="Light is already on"):
        await turn_on_tool.run(arguments={"minutes": 30})

    # Note: Cooldown timing constraint is extensively tested in test_light.py with freezegun
    # We don't test it here because it would require waiting 30 real minutes between tests

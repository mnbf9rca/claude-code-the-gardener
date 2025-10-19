"""
Unit Tests for Light Module

These tests verify the light control functionality including:
- Turning light on/off
- Timing constraint enforcement
- Status reporting
- Home Assistant integration (mocked)
"""
import pytest
import pytest_asyncio
import json
import httpx
from datetime import datetime, timedelta, timezone
from freezegun import freeze_time
from fastmcp import FastMCP
import tools.light as light_module
from tools.light import setup_light_tools
from shared_state import reset_cycle, current_cycle_status
from pytest_httpx import HTTPXMock

# Apply to all tests in this module
pytestmark = pytest.mark.httpx_mock(assert_all_responses_were_requested=False)


@pytest_asyncio.fixture(autouse=True)
async def setup_light_state(httpx_mock: HTTPXMock):
    """Reset light state before each test and setup HA mocks"""
    # Reset cycle state
    reset_cycle()
    current_cycle_status["written"] = True  # Allow tool calls

    # Reset light state
    light_module.light_state["status"] = "off"
    light_module.light_state["last_on"] = None
    light_module.light_state["last_off"] = None
    light_module.light_state["scheduled_off"] = None

    # Reset light history (uses JsonlHistory utility)
    light_module.light_history.clear()
    light_module.light_history._loaded = False

    # Reset state loaded flag
    light_module._state_loaded = False

    # Clear persisted state and history files
    light_module.STATE_FILE.unlink(missing_ok=True)
    light_module.light_history.file_path.unlink(missing_ok=True)

    # Reset HTTP client to ensure clean state
    light_module.http_client = None

    # Setup default Home Assistant mocks
    # Note: Using callbacks and adding them multiple times to allow reuse
    def mock_turn_on(request):
        return httpx.Response(200, json=[{"entity_id": light_module.LIGHT_ENTITY_ID, "state": "on"}])

    def mock_turn_off(request):
        return httpx.Response(200, json=[{"entity_id": light_module.LIGHT_ENTITY_ID, "state": "off"}])

    def mock_get_state(request):
        return httpx.Response(200, json={"entity_id": light_module.LIGHT_ENTITY_ID, "state": light_module.light_state["status"]})

    # Add each callback multiple times to allow reuse
    for _ in range(20):  # Enough for most tests
        httpx_mock.add_callback(mock_turn_on, url=f"{light_module.HA_URL}/api/services/switch/turn_on")
        httpx_mock.add_callback(mock_turn_off, url=f"{light_module.HA_URL}/api/services/switch/turn_off")
        httpx_mock.add_callback(mock_get_state, url=f"{light_module.HA_URL}/api/states/{light_module.LIGHT_ENTITY_ID}")

    # Create MCP instance and setup tools
    mcp = FastMCP("test")
    setup_light_tools(mcp)

    yield mcp

    # Cleanup
    if light_module.http_client:
        await light_module.http_client.aclose()
        light_module.http_client = None


@pytest.mark.asyncio
async def test_turn_on_basic(setup_light_state):
    """Test basic light activation"""
    mcp = setup_light_state
    turn_on_tool = mcp._tool_manager._tools["turn_on_light"]

    tool_result = await turn_on_tool.run(arguments={"minutes": 60})
    result = json.loads(tool_result.content[0].text)

    assert result["status"] == "on"
    assert result["duration_minutes"] == 60
    assert "off_at" in result
    assert light_module.light_state["status"] == "on"


@pytest.mark.asyncio
async def test_turn_on_min_max_duration(setup_light_state):
    """Test minimum and maximum duration limits"""
    mcp = setup_light_state
    turn_on_tool = mcp._tool_manager._tools["turn_on_light"]
    status_tool = mcp._tool_manager._tools["get_light_status"]

    # Test minimum (30 minutes)
    tool_result = await turn_on_tool.run(arguments={"minutes": 30})
    result = json.loads(tool_result.content[0].text)
    assert result["duration_minutes"] == 30

    # Wait for auto-off
    with freeze_time("2024-01-01 12:00:00") as frozen_time:
        light_module.light_state["status"] = "off"
        light_module.light_state["last_off"] = datetime.now(timezone.utc).isoformat()
        light_module.light_state["scheduled_off"] = None

        # Wait minimum off time
        frozen_time.move_to("2024-01-01 12:31:00")

        # Test maximum (120 minutes)
        tool_result = await turn_on_tool.run(arguments={"minutes": 120})
        result = json.loads(tool_result.content[0].text)
        assert result["duration_minutes"] == 120


@pytest.mark.asyncio
async def test_turn_on_validation(setup_light_state):
    """Test that invalid durations are rejected"""
    mcp = setup_light_state
    turn_on_tool = mcp._tool_manager._tools["turn_on_light"]

    # Test below minimum
    with pytest.raises(Exception):  # Pydantic validation error
        await turn_on_tool.run(arguments={"minutes": 20})

    # Test above maximum
    with pytest.raises(Exception):  # Pydantic validation error
        await turn_on_tool.run(arguments={"minutes": 150})


@pytest.mark.asyncio
async def test_turn_on_validation_non_integer_values(setup_light_state):
    """Test that non-integer and invalid duration values are rejected"""
    mcp = setup_light_state
    turn_on_tool = mcp._tool_manager._tools["turn_on_light"]

    # Test string value
    with pytest.raises(Exception):  # Pydantic validation error
        await turn_on_tool.run(arguments={"minutes": "sixty"})

    # Test float value
    with pytest.raises(Exception):  # Pydantic validation error
        await turn_on_tool.run(arguments={"minutes": 45.5})

    # Test None value
    with pytest.raises(Exception):  # Pydantic validation error
        await turn_on_tool.run(arguments={"minutes": None})

    # Test negative value
    with pytest.raises(Exception):  # Pydantic validation error
        await turn_on_tool.run(arguments={"minutes": -30})


@pytest.mark.asyncio
async def test_cannot_turn_on_when_already_on(setup_light_state):
    """Test that light cannot be turned on when already on"""
    mcp = setup_light_state
    turn_on_tool = mcp._tool_manager._tools["turn_on_light"]

    # Turn on light
    await turn_on_tool.run(arguments={"minutes": 60})

    # Try to turn on again
    with pytest.raises(ValueError, match="Light is already on"):
        await turn_on_tool.run(arguments={"minutes": 30})


@pytest.mark.asyncio
async def test_minimum_off_time_enforcement(setup_light_state):
    """Test that 30 minutes off time is enforced between activations"""
    mcp = setup_light_state
    turn_on_tool = mcp._tool_manager._tools["turn_on_light"]

    with freeze_time("2024-01-01 12:00:00") as frozen_time:
        # Turn on light
        await turn_on_tool.run(arguments={"minutes": 30})

        # Simulate light turning off
        light_module.light_state["status"] = "off"
        light_module.light_state["last_off"] = datetime.now(timezone.utc).isoformat()
        light_module.light_state["scheduled_off"] = None

        # Try to turn on immediately
        with pytest.raises(ValueError, match="requires 30 minutes off"):
            await turn_on_tool.run(arguments={"minutes": 30})

        # Move forward 29 minutes (still too soon)
        frozen_time.move_to("2024-01-01 12:29:00")
        with pytest.raises(ValueError, match="Wait 1 more minutes"):
            await turn_on_tool.run(arguments={"minutes": 30})

        # Move forward to exactly 30 minutes
        frozen_time.move_to("2024-01-01 12:30:00")
        tool_result = await turn_on_tool.run(arguments={"minutes": 30})
        result = json.loads(tool_result.content[0].text)
        assert result["status"] == "on"


@pytest.mark.asyncio
async def test_get_light_status(setup_light_state):
    """Test getting light status"""
    mcp = setup_light_state
    turn_on_tool = mcp._tool_manager._tools["turn_on_light"]
    status_tool = mcp._tool_manager._tools["get_light_status"]

    # Check initial status
    tool_result = await status_tool.run(arguments={})
    result = json.loads(tool_result.content[0].text)
    assert result["status"] == "off"
    assert result["can_activate"] is True
    assert result["minutes_until_available"] == 0
    assert result["last_on"] is None
    assert result["last_off"] is None

    # Turn on light
    with freeze_time("2024-01-01 12:00:00"):
        await turn_on_tool.run(arguments={"minutes": 60})

        tool_result = await status_tool.run(arguments={})
        result = json.loads(tool_result.content[0].text)
        assert result["status"] == "on"
        assert result["can_activate"] is False
        assert result["minutes_until_available"] > 0
        assert result["last_on"] is not None


@pytest.mark.asyncio
async def test_auto_off_simulation(setup_light_state):
    """Test that light auto-turns off after scheduled time"""
    mcp = setup_light_state
    turn_on_tool = mcp._tool_manager._tools["turn_on_light"]
    status_tool = mcp._tool_manager._tools["get_light_status"]

    with freeze_time("2024-01-01 12:00:00") as frozen_time:
        # Turn on for 30 minutes
        await turn_on_tool.run(arguments={"minutes": 30})
        assert light_module.light_state["status"] == "on"

        # Check status before scheduled off time
        tool_result = await status_tool.run(arguments={})
        result = json.loads(tool_result.content[0].text)
        assert result["status"] == "on"

        # Move past scheduled off time
        frozen_time.move_to("2024-01-01 12:31:00")

        # Check status should trigger auto-off
        tool_result = await status_tool.run(arguments={})
        result = json.loads(tool_result.content[0].text)
        assert result["status"] == "off"
        assert light_module.light_state["status"] == "off"
        assert light_module.light_state["last_off"] is not None


@pytest.mark.asyncio
async def test_availability_calculation(setup_light_state):
    """Test availability calculation for next activation"""
    mcp = setup_light_state
    turn_on_tool = mcp._tool_manager._tools["turn_on_light"]
    status_tool = mcp._tool_manager._tools["get_light_status"]

    with freeze_time("2024-01-01 12:00:00") as frozen_time:
        # Turn on light for 30 minutes
        await turn_on_tool.run(arguments={"minutes": 30})

        # Check availability while on
        tool_result = await status_tool.run(arguments={})
        result = json.loads(tool_result.content[0].text)
        assert not result["can_activate"]
        assert result["minutes_until_available"] >= 29

        # Move to when light turns off
        frozen_time.move_to("2024-01-01 12:30:00")
        await status_tool.run(arguments={})  # Trigger auto-off

        # Check availability right after off
        tool_result = await status_tool.run(arguments={})
        result = json.loads(tool_result.content[0].text)
        assert not result["can_activate"]
        assert result["minutes_until_available"] == 30

        # Move 15 minutes forward
        frozen_time.move_to("2024-01-01 12:45:00")
        tool_result = await status_tool.run(arguments={})
        result = json.loads(tool_result.content[0].text)
        assert not result["can_activate"]
        assert result["minutes_until_available"] == 15

        # Move to 30 minutes after off
        frozen_time.move_to("2024-01-01 13:00:00")
        tool_result = await status_tool.run(arguments={})
        result = json.loads(tool_result.content[0].text)
        assert result["can_activate"]
        assert result["minutes_until_available"] == 0


@pytest.mark.asyncio
async def test_gatekeeper_enforcement(setup_light_state):
    """Test that plant status must be written first"""
    mcp = setup_light_state
    turn_on_tool = mcp._tool_manager._tools["turn_on_light"]

    # Reset the cycle status
    current_cycle_status["written"] = False

    with pytest.raises(ValueError, match="Must call write_status first"):
        await turn_on_tool.run(arguments={"minutes": 60})


@pytest.mark.asyncio
async def test_turn_off_basic(setup_light_state):
    """Test basic turn_off functionality"""
    mcp = setup_light_state
    turn_on_tool = mcp._tool_manager._tools["turn_on_light"]
    turn_off_tool = mcp._tool_manager._tools["turn_off_light"]

    # Turn on the light first
    await turn_on_tool.run(arguments={"minutes": 60})
    assert light_module.light_state["status"] == "on"

    # Turn it off
    tool_result = await turn_off_tool.run(arguments={})
    result = json.loads(tool_result.content[0].text)

    assert result["status"] == "off"
    assert "turned_off_at" in result
    assert result["message"] == "Light turned off successfully"
    assert light_module.light_state["status"] == "off"
    assert light_module.light_state["scheduled_off"] is None


@pytest.mark.asyncio
async def test_turn_off_gatekeeper(setup_light_state):
    """Test that turn_off requires plant status to be written"""
    mcp = setup_light_state
    turn_off_tool = mcp._tool_manager._tools["turn_off_light"]

    # Reset the cycle status
    current_cycle_status["written"] = False

    with pytest.raises(ValueError, match="Must call write_status first"):
        await turn_off_tool.run(arguments={})


@pytest.mark.asyncio
async def test_ha_service_failure_turn_on(setup_light_state, httpx_mock: HTTPXMock):
    """Test graceful handling when Home Assistant turn_on fails"""
    mcp = setup_light_state
    turn_on_tool = mcp._tool_manager._tools["turn_on_light"]

    # Clear existing mocks and add a failure callback
    httpx_mock.reset()

    def mock_turn_on_fail(request):
        return httpx.Response(500, json={"error": "Internal Server Error"})

    httpx_mock.add_callback(mock_turn_on_fail, url=f"{light_module.HA_URL}/api/services/switch/turn_on")

    # Should raise error when HA fails
    with pytest.raises(ValueError, match="Failed to communicate with Home Assistant"):
        await turn_on_tool.run(arguments={"minutes": 60})

    # State should not be updated
    assert light_module.light_state["status"] == "off"


@pytest.mark.asyncio
async def test_ha_service_failure_turn_off(setup_light_state, httpx_mock: HTTPXMock):
    """Test graceful handling when Home Assistant turn_off fails"""
    mcp = setup_light_state
    turn_on_tool = mcp._tool_manager._tools["turn_on_light"]
    turn_off_tool = mcp._tool_manager._tools["turn_off_light"]

    # Turn on the light
    await turn_on_tool.run(arguments={"minutes": 60})

    # Clear mocks and add a failure callback for turn_off
    httpx_mock.reset()

    def mock_turn_off_fail(request):
        return httpx.Response(500, json={"error": "Internal Server Error"})

    httpx_mock.add_callback(mock_turn_off_fail, url=f"{light_module.HA_URL}/api/services/switch/turn_off")

    # Should raise error when HA fails
    with pytest.raises(ValueError, match="Failed to communicate with Home Assistant"):
        await turn_off_tool.run(arguments={})

    # State should still be on (not updated due to failure)
    assert light_module.light_state["status"] == "on"


@pytest.mark.asyncio
async def test_get_status_syncs_with_ha(setup_light_state, httpx_mock: HTTPXMock):
    """Test that get_light_status syncs with Home Assistant state"""
    mcp = setup_light_state
    status_tool = mcp._tool_manager._tools["get_light_status"]

    # Clear mocks and set HA state to 'on'
    httpx_mock.reset()

    def mock_get_state_on(request):
        return httpx.Response(200, json={"entity_id": light_module.LIGHT_ENTITY_ID, "state": "on"})

    httpx_mock.add_callback(mock_get_state_on, url=f"{light_module.HA_URL}/api/states/{light_module.LIGHT_ENTITY_ID}")

    # Local state says off, but HA says on
    assert light_module.light_state["status"] == "off"

    # Check status should sync with HA
    tool_result = await status_tool.run(arguments={})
    result = json.loads(tool_result.content[0].text)

    # Should now reflect HA state
    assert result["status"] == "on"
    assert light_module.light_state["status"] == "on"


@pytest.mark.asyncio
async def test_auto_off_calls_ha(setup_light_state):
    """Test that auto-off triggers Home Assistant turn_off and updates state"""
    mcp = setup_light_state
    turn_on_tool = mcp._tool_manager._tools["turn_on_light"]
    status_tool = mcp._tool_manager._tools["get_light_status"]

    with freeze_time("2024-01-01 12:00:00") as frozen_time:
        # Turn on for 30 minutes
        await turn_on_tool.run(arguments={"minutes": 30})
        assert light_module.light_state["status"] == "on"
        assert light_module.light_state["scheduled_off"] is not None

        # Move past scheduled off time
        frozen_time.move_to("2024-01-01 12:31:00")

        # Check status should trigger auto-off
        tool_result = await status_tool.run(arguments={})
        result = json.loads(tool_result.content[0].text)

        # Verify auto-off happened
        assert result["status"] == "off"
        assert light_module.light_state["status"] == "off"
        assert light_module.light_state["scheduled_off"] is None
        assert light_module.light_state["last_off"] is not None
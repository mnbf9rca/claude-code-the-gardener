"""
Unit Tests for Light Module

These tests verify the light control functionality including:
- Turning light on/off
- Timing constraint enforcement
- Status reporting
"""
import pytest
import pytest_asyncio
import json
from datetime import datetime, timedelta
from freezegun import freeze_time
from fastmcp import FastMCP
import tools.light as light_module
from tools.light import setup_light_tools
from shared_state import reset_cycle, current_cycle_status


@pytest_asyncio.fixture(autouse=True)
async def setup_light_state():
    """Reset light state before each test"""
    # Reset cycle state
    reset_cycle()
    current_cycle_status["written"] = True  # Allow tool calls

    # Reset light state
    light_module.light_state["status"] = "off"
    light_module.light_state["last_on"] = None
    light_module.light_state["last_off"] = None
    light_module.light_state["scheduled_off"] = None

    # Create MCP instance and setup tools
    mcp = FastMCP("test")
    setup_light_tools(mcp)

    yield mcp


@pytest.mark.asyncio
async def test_turn_on_basic(setup_light_state):
    """Test basic light activation"""
    mcp = setup_light_state
    turn_on_tool = mcp._tool_manager._tools["turn_on"]

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
    turn_on_tool = mcp._tool_manager._tools["turn_on"]
    status_tool = mcp._tool_manager._tools["get_light_status"]

    # Test minimum (30 minutes)
    tool_result = await turn_on_tool.run(arguments={"minutes": 30})
    result = json.loads(tool_result.content[0].text)
    assert result["duration_minutes"] == 30

    # Wait for auto-off
    with freeze_time("2024-01-01 12:00:00") as frozen_time:
        light_module.light_state["status"] = "off"
        light_module.light_state["last_off"] = datetime.now().isoformat()
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
    turn_on_tool = mcp._tool_manager._tools["turn_on"]

    # Test below minimum
    with pytest.raises(Exception):  # Pydantic validation error
        await turn_on_tool.run(arguments={"minutes": 20})

    # Test above maximum
    with pytest.raises(Exception):  # Pydantic validation error
        await turn_on_tool.run(arguments={"minutes": 150})


@pytest.mark.asyncio
async def test_cannot_turn_on_when_already_on(setup_light_state):
    """Test that light cannot be turned on when already on"""
    mcp = setup_light_state
    turn_on_tool = mcp._tool_manager._tools["turn_on"]

    # Turn on light
    await turn_on_tool.run(arguments={"minutes": 60})

    # Try to turn on again
    with pytest.raises(ValueError, match="Light is already on"):
        await turn_on_tool.run(arguments={"minutes": 30})


@pytest.mark.asyncio
async def test_minimum_off_time_enforcement(setup_light_state):
    """Test that 30 minutes off time is enforced between activations"""
    mcp = setup_light_state
    turn_on_tool = mcp._tool_manager._tools["turn_on"]

    with freeze_time("2024-01-01 12:00:00") as frozen_time:
        # Turn on light
        await turn_on_tool.run(arguments={"minutes": 30})

        # Simulate light turning off
        light_module.light_state["status"] = "off"
        light_module.light_state["last_off"] = datetime.now().isoformat()
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
    turn_on_tool = mcp._tool_manager._tools["turn_on"]
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
    turn_on_tool = mcp._tool_manager._tools["turn_on"]
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
    turn_on_tool = mcp._tool_manager._tools["turn_on"]
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
    turn_on_tool = mcp._tool_manager._tools["turn_on"]

    # Reset the cycle status
    current_cycle_status["written"] = False

    with pytest.raises(ValueError, match="Must call write_status first"):
        await turn_on_tool.run(arguments={"minutes": 60})
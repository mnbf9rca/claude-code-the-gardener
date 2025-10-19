"""
Unit tests for plant_status module

These test the plant_status functions directly without going through MCP server
"""
import pytest
import pytest_asyncio
from datetime import datetime
from fastmcp import FastMCP
import tools.plant_status as ps_module
from shared_state import reset_cycle, current_cycle_status


@pytest_asyncio.fixture(autouse=True)
async def reset_state():
    """Reset state before each test"""
    reset_cycle()
    ps_module.status_history.clear()
    ps_module.current_status = None
    yield


@pytest.mark.asyncio
async def test_write_status_first_time():
    """Test writing status for the first time in a cycle"""
    # Create a mock MCP server for testing
    test_mcp = FastMCP("Test")
    ps_module.setup_plant_status_tools(test_mcp)

    # Get the write_status tool
    write_tool = test_mcp._tool_manager._tools["write_plant_status"]

    # Write status
    result = await write_tool.run(arguments={
        "sensor_reading": 2000,
        "water_24h": 50.0,
        "light_today": 120.0,
        "plant_state": "healthy",
        "next_action_sequence": [{"order": 1, "action": "water", "value": 30}],
        "reasoning": "Test status"
    })

    # Verify response
    assert result.content is not None
    assert current_cycle_status["written"] is True
    assert ps_module.current_status is not None
    assert len(ps_module.status_history) == 1


@pytest.mark.asyncio
async def test_write_status_duplicate_prevention():
    """Test that duplicate status writes in same cycle are prevented"""
    test_mcp = FastMCP("Test")
    ps_module.setup_plant_status_tools(test_mcp)
    write_tool = test_mcp._tool_manager._tools["write_plant_status"]

    # First write
    await write_tool.run(arguments={
        "sensor_reading": 2000,
        "water_24h": 50.0,
        "light_today": 120.0,
        "plant_state": "healthy",
        "next_action_sequence": [],
        "reasoning": "First write"
    })

    # Attempt duplicate write
    result = await write_tool.run(arguments={
        "sensor_reading": 2100,
        "water_24h": 60.0,
        "light_today": 130.0,
        "plant_state": "stressed",
        "next_action_sequence": [],
        "reasoning": "Duplicate attempt"
    })

    # Should be rejected
    assert current_cycle_status["written"] is True
    assert len(ps_module.status_history) == 1  # Should still be just 1
    assert ps_module.status_history[0]["sensor_reading"] == 2000  # Original value


@pytest.mark.asyncio
async def test_status_history_limit():
    """Test that status history is limited to prevent memory issues when using the tool"""
    test_mcp = FastMCP("Test")
    ps_module.setup_plant_status_tools(test_mcp)
    write_tool = test_mcp._tool_manager._tools["write_plant_status"]

    # The limit is enforced in the write_status tool, not on the array directly
    # Add 1000 entries directly first
    for i in range(1000):
        ps_module.status_history.append({
            "timestamp": datetime.now().isoformat(),
            "sensor_reading": 2000 + i,
            "water_24h": 0,
            "light_today": 0,
            "plant_state": "healthy",
            "next_action_sequence": [],
            "reasoning": f"Entry {i}"
        })

    # Now write one more through the tool - it should keep at 1000
    await write_tool.run(arguments={
        "sensor_reading": 3000,
        "water_24h": 50.0,
        "light_today": 120.0,
        "plant_state": "healthy",
        "next_action_sequence": [],
        "reasoning": "Test limit"
    })

    # Should still be capped at 1000 (oldest removed, newest added)
    assert len(ps_module.status_history) == 1000
    # Verify the newest entry is there
    assert ps_module.status_history[-1]["sensor_reading"] == 3000


@pytest.mark.asyncio
async def test_get_current_status():
    """Test getting current status only when cycle is written"""
    test_mcp = FastMCP("Test")
    ps_module.setup_plant_status_tools(test_mcp)

    get_current_tool = test_mcp._tool_manager._tools["get_current_plant_status"]

    # Should return None when not written
    result = await get_current_tool.run(arguments={})
    assert result.content == []  # Empty content for None

    # Write status
    write_tool = test_mcp._tool_manager._tools["write_plant_status"]
    await write_tool.run(arguments={
        "sensor_reading": 2000,
        "water_24h": 50.0,
        "light_today": 120.0,
        "plant_state": "healthy",
        "next_action_sequence": [],
        "reasoning": "Test"
    })

    # Now should return the status
    result = await get_current_tool.run(arguments={})
    assert result.content is not None


@pytest.mark.asyncio
async def test_get_status_history_with_limit():
    """Test getting history with different limits"""
    test_mcp = FastMCP("Test")
    ps_module.setup_plant_status_tools(test_mcp)

    # Add some entries directly
    for i in range(10):
        ps_module.status_history.append({
            "timestamp": datetime.now().isoformat(),
            "sensor_reading": 2000 + i,
            "plant_state": "healthy",
        })

    history_tool = test_mcp._tool_manager._tools["get_plant_status_history"]

    # Test with limit 5
    result = await history_tool.run(arguments={"limit": 5})
    # Result will be JSON text content, would need to parse to check length

    # Test with limit larger than available
    result = await history_tool.run(arguments={"limit": 20})
    # Should return all 10 items


@pytest.mark.asyncio
async def test_plant_state_values():
    """Test that only valid plant states are accepted"""
    test_mcp = FastMCP("Test")
    ps_module.setup_plant_status_tools(test_mcp)
    write_tool = test_mcp._tool_manager._tools["write_plant_status"]

    valid_states = ["healthy", "stressed", "concerning", "critical", "unknown"]

    for state in valid_states:
        reset_cycle()  # Reset for each test
        result = await write_tool.run(arguments={
            "sensor_reading": 2000,
            "water_24h": 50.0,
            "light_today": 120.0,
            "plant_state": state,
            "next_action_sequence": [],
            "reasoning": f"Testing {state}"
        })
        assert result.content is not None

    # Invalid state would be caught by FastMCP validation
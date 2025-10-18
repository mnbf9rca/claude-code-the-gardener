"""
Integration Tests for Plant Care MCP Server

These tests verify the complete MCP server functionality with all components
working together. They test through the MCP server interface, not individual modules.

For unit tests of individual modules, see:
- test_plant_status.py - Unit tests for plant status module
- test_moisture_sensor.py - Unit tests for moisture sensor module
"""
import pytest
import pytest_asyncio
import json
from server import mcp
from shared_state import reset_cycle
import tools.plant_status as ps_module
import tools.moisture_sensor as ms_module


@pytest_asyncio.fixture(autouse=True)
async def reset_server_state():
    """Setup/teardown fixture to reset server state before each test"""
    # Reset cycle state
    reset_cycle()

    # Reset plant status history and current status
    ps_module.status_history.clear()
    ps_module.current_status = None

    # Reset moisture sensor history and mock value
    ms_module.sensor_history.clear()
    ms_module.mock_sensor_value = 2000

    yield
    # Teardown if needed (currently no cleanup required)


@pytest.mark.asyncio
async def test_server_initialization():
    """Test that the server initializes with expected tools"""
    # Get list of available tools - FastMCP v2 uses _tools (private attr)
    tools = [tool.name for tool in mcp._tool_manager._tools.values()]

    # Check that our core tools are present
    assert "write_status" in tools
    assert "get_current_status" in tools
    assert "get_status_history" in tools
    assert "read_moisture" in tools
    assert "get_sensor_history" in tools
    assert "simulate_watering" in tools

    print(f"✓ Server initialized with {len(tools)} tools")


@pytest.mark.asyncio
async def test_gatekeeper_enforcement():
    """Test that moisture sensor requires plant status to be written first"""
    # Try to read moisture without writing status first
    moisture_tool = mcp._tool_manager._tools["read_moisture"]

    with pytest.raises(ValueError) as exc_info:
        result = await moisture_tool.run(arguments={})
        # The error might be in the ToolResult, so check for that
        if hasattr(result, 'error'):
            raise ValueError(result.error)

    assert "Must call write_status first" in str(exc_info.value)
    print("✓ Gatekeeper properly enforces status-first requirement")


@pytest.mark.asyncio
async def test_write_status_and_read_sensor():
    """Test the basic flow of writing status then reading sensor"""
    # Write plant status
    write_status_tool = mcp._tool_manager._tools["write_status"]
    tool_result = await write_status_tool.run(arguments={
        "sensor_reading": 2000,
        "water_24h": 100.0,
        "light_today": 240.0,
        "plant_state": "healthy",
        "next_action_sequence": [
            {"order": 1, "action": "observe", "value": None}
        ],
        "reasoning": "Plant appears healthy, monitoring only"
    })
    # Parse the JSON from the TextContent
    result = json.loads(tool_result.content[0].text)

    assert result["proceed"] is True
    assert "timestamp" in result
    print("✓ Successfully wrote plant status")

    # Now moisture reading should work
    moisture_tool = mcp._tool_manager._tools["read_moisture"]
    tool_result = await moisture_tool.run(arguments={})
    reading = json.loads(tool_result.content[0].text)

    assert "value" in reading
    assert "timestamp" in reading
    assert 1500 <= reading["value"] <= 3500  # Reasonable range
    print(f"✓ Successfully read moisture: {reading['value']}")


@pytest.mark.asyncio
async def test_status_history_with_data():
    """Test that status history is maintained"""
    # First write a status to have something in history
    write_status_tool = mcp._tool_manager._tools["write_status"]
    await write_status_tool.run(arguments={
        "sensor_reading": 2100,
        "water_24h": 50.0,
        "light_today": 120.0,
        "plant_state": "healthy",
        "next_action_sequence": [],
        "reasoning": "Test status for history"
    })

    # Get history
    history_tool = mcp._tool_manager._tools["get_status_history"]
    tool_result = await history_tool.run(arguments={"limit": 5})
    history = json.loads(tool_result.content[0].text)

    # Should have exactly one entry
    assert isinstance(history, list)
    assert len(history) == 1
    assert "timestamp" in history[0]
    assert "plant_state" in history[0]
    assert history[0]["plant_state"] == "healthy"
    print(f"✓ Status history maintained: {len(history)} records")


@pytest.mark.asyncio
async def test_empty_status_history():
    """Test that an empty status history returns an empty list without errors"""
    # Ensure history is really empty by accessing the module directly
    ps_module.status_history.clear()

    # Get history when empty
    history_tool = mcp._tool_manager._tools["get_status_history"]
    tool_result = await history_tool.run(arguments={"limit": 5})

    # Handle case where content might be empty or have text
    if tool_result.content and len(tool_result.content) > 0:
        history = json.loads(tool_result.content[0].text)
    else:
        history = []  # Treat empty content as empty list

    assert isinstance(history, list)
    assert len(history) == 0, f"Expected empty history but got {len(history)} items: {history}"
    print("✓ Empty status history returns empty list without errors")


@pytest.mark.asyncio
async def test_duplicate_status_prevention():
    """Test that status can't be written twice in same cycle"""
    write_status_tool = mcp._tool_manager._tools["write_status"]

    # Write status first time
    await write_status_tool.run(arguments={
        "sensor_reading": 2000,
        "water_24h": 100.0,
        "light_today": 240.0,
        "plant_state": "healthy",
        "next_action_sequence": [],
        "reasoning": "First write"
    })

    # Try to write status again in same cycle
    tool_result = await write_status_tool.run(arguments={
        "sensor_reading": 1900,
        "water_24h": 100.0,
        "light_today": 240.0,
        "plant_state": "healthy",
        "next_action_sequence": [],
        "reasoning": "Duplicate test"
    })
    result = json.loads(tool_result.content[0].text)

    assert result["proceed"] is False
    assert "already written" in result["reason"].lower()
    print("✓ Duplicate status write properly prevented")


@pytest.mark.asyncio
async def test_sensor_history_sampling():
    """Test that sensor history sampling works correctly"""
    # First enable writing by setting status
    write_status_tool = mcp._tool_manager._tools["write_status"]
    await write_status_tool.run(arguments={
        "sensor_reading": 2000,
        "water_24h": 0,
        "light_today": 0,
        "plant_state": "healthy",
        "next_action_sequence": [],
        "reasoning": "Test setup"
    })

    # Add multiple sensor readings
    moisture_tool = mcp._tool_manager._tools["read_moisture"]
    for _ in range(10):
        await moisture_tool.run(arguments={})

    # Get sensor history
    history_tool = mcp._tool_manager._tools["get_sensor_history"]
    tool_result = await history_tool.run(arguments={"hours": 1})
    history = json.loads(tool_result.content[0].text)

    assert isinstance(history, list)
    assert len(history) > 0
    # Check structure of returned data
    if history:
        assert len(history[0]) == 2  # [timestamp, value] pairs
    print(f"✓ Sensor history sampling works: {len(history)} samples")


# Use pytest to run tests instead of custom runner
if __name__ == "__main__":
    # Run with: pytest test_server.py -v
    pytest.main([__file__, "-v"])
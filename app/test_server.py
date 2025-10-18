"""
Basic smoke tests for Plant Care MCP Server
"""
import pytest
import asyncio
import json
from datetime import datetime
from server import mcp
from shared_state import reset_cycle


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

    print(f"✓ Server initialized with {len(tools)} tools")


@pytest.mark.asyncio
async def test_gatekeeper_enforcement():
    """Test that moisture sensor requires plant status to be written first"""
    # Reset the cycle
    reset_cycle()

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
    # Reset the cycle
    reset_cycle()

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
async def test_status_history():
    """Test that status history is maintained"""
    # Get history
    history_tool = mcp._tool_manager._tools["get_status_history"]
    tool_result = await history_tool.run(arguments={"limit": 5})
    history = json.loads(tool_result.content[0].text)

    # Should have at least one entry from previous test
    assert isinstance(history, list)
    if history:
        assert "timestamp" in history[0]
        assert "plant_state" in history[0]
    print(f"✓ Status history maintained: {len(history)} records")


@pytest.mark.asyncio
async def test_duplicate_status_prevention():
    """Test that status can't be written twice in same cycle"""
    # Don't reset cycle - use existing one from previous test
    write_status_tool = mcp._tool_manager._tools["write_status"]

    # Try to write status again
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


def run_tests():
    """Run all tests"""
    print("\n=== Plant Care MCP Server Tests ===\n")

    # Run tests in order
    asyncio.run(test_server_initialization())
    asyncio.run(test_gatekeeper_enforcement())
    asyncio.run(test_write_status_and_read_sensor())
    asyncio.run(test_status_history())
    asyncio.run(test_duplicate_status_prevention())

    print("\n✅ All tests passed!\n")


if __name__ == "__main__":
    run_tests()
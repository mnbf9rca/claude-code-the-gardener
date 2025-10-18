"""
Simple Manual Test for Debugging FastMCP Server

PURPOSE:
- Manual smoke test for quick debugging during development
- Helps understand FastMCP tool structure and response format
- NOT part of the automated test suite (use pytest test_*.py for that)
- Useful for testing server changes without full pytest overhead

USAGE:
    uv run python simple_test.py

This is intentionally separate from the pytest test suite to allow
quick manual testing and debugging of the MCP server behavior.
"""
import asyncio
import json
from fastmcp.tools.tool import FunctionTool
from server import mcp
from shared_state import reset_cycle

async def test_tools():
    # Reset cycle
    reset_cycle()

    # List tools
    tools = mcp._tool_manager._tools
    print(f"Available tools: {list(tools.keys())}")

    # Assert that tools are available
    assert isinstance(tools, dict), "Tools should be a dictionary"
    assert "write_status" in tools, "'write_status' tool should be available"
    assert "read_moisture" in tools, "'read_moisture' tool should be available"
    assert len(tools) > 0, "Tool manager should not be empty"

    # Get the write_status tool
    write_status_tool = tools["write_status"]
    print(f"Tool type: {type(write_status_tool)}")

    # Assert the type of write_status_tool
    assert isinstance(write_status_tool, FunctionTool), "write_status_tool should be a FunctionTool"

    # Try to call it using run method with arguments parameter
    try:
        result = await write_status_tool.run(arguments={
            "sensor_reading": 2000,
            "water_24h": 100.0,
            "light_today": 240.0,
            "plant_state": "healthy",
            "next_action_sequence": [{"order": 1, "action": "observe", "value": None}],
            "reasoning": "Testing"
        })

        # Assert status write result
        assert result is not None, "Status write should return a result"
        assert hasattr(result, 'content'), "Result should have content attribute"
        assert len(result.content) > 0, "Result content should not be empty"

        # Parse and validate the JSON response
        status_data = json.loads(result.content[0].text)
        assert status_data["proceed"] is True, "Status write should allow proceeding"
        assert "timestamp" in status_data, "Status should include timestamp"

        print(f"✓ Status written successfully: proceed={status_data['proceed']}")

        # Now try reading moisture
        moisture_tool = tools["read_moisture"]
        reading = await moisture_tool.run(arguments={})

        # Assert moisture reading result
        assert reading is not None, "Moisture reading should return a result"
        assert hasattr(reading, 'content'), "Reading should have content attribute"

        # Parse and validate moisture data
        moisture_data = json.loads(reading.content[0].text)
        assert "value" in moisture_data, "Moisture data should have value"
        assert "timestamp" in moisture_data, "Moisture data should have timestamp"
        assert 1500 <= moisture_data["value"] <= 3500, f"Moisture value {moisture_data['value']} should be in reasonable range"

        print(f"✓ Moisture reading successful: value={moisture_data['value']}")
        print("✅ All assertions passed!")

    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        raise

if __name__ == "__main__":
    asyncio.run(test_tools())
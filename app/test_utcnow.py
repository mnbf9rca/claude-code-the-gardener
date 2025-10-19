"""
Unit tests for utcnow module

Tests the UTC time query tool
"""
import json
import pytest
import pytest_asyncio
from fastmcp import FastMCP
from mcp.types import TextContent
from datetime import datetime, timezone
import tools.utcnow as utcnow_module


@pytest.mark.asyncio
async def test_get_current_time_returns_timestamp():
    """Test that get_current_time returns a timestamp"""
    test_mcp = FastMCP("Test")
    utcnow_module.setup_utcnow_tools(test_mcp)

    get_time_tool = test_mcp._tool_manager._tools["get_current_time"]

    # Call the tool
    result = await get_time_tool.run(arguments={})

    # Should return content with timestamp
    assert result.content is not None
    assert "timestamp" in str(result.content)


@pytest.mark.asyncio
async def test_get_current_time_returns_valid_iso8601():
    """Test that returned timestamp is valid ISO8601 format"""
    test_mcp = FastMCP("Test")
    utcnow_module.setup_utcnow_tools(test_mcp)

    get_time_tool = test_mcp._tool_manager._tools["get_current_time"]

    # Call the tool
    result = await get_time_tool.run(arguments={})

    # Extract JSON from the TextContent object
    assert len(result.content) > 0, "Result content is empty"
    content_item = result.content[0]
    assert isinstance(content_item, TextContent), f"Expected TextContent, got {type(content_item)}"
    text_content = content_item.text

    # Parse the JSON response
    response_data = json.loads(text_content)

    # Extract timestamp value
    assert "timestamp" in response_data, f"No 'timestamp' key in response: {response_data}"
    timestamp_str = response_data["timestamp"]

    # Validate ISO8601 format by parsing it
    parsed_timestamp = datetime.fromisoformat(timestamp_str)
    assert isinstance(parsed_timestamp, datetime)


@pytest.mark.asyncio
async def test_get_current_time_returns_utc():
    """Test that returned timestamp is in UTC timezone"""
    test_mcp = FastMCP("Test")
    utcnow_module.setup_utcnow_tools(test_mcp)

    get_time_tool = test_mcp._tool_manager._tools["get_current_time"]

    # Call the tool
    result = await get_time_tool.run(arguments={})

    # Extract JSON from the TextContent object
    assert len(result.content) > 0, "Result content is empty"
    content_item = result.content[0]
    assert isinstance(content_item, TextContent), f"Expected TextContent, got {type(content_item)}"
    text_content = content_item.text

    # Parse the JSON response
    response_data = json.loads(text_content)
    timestamp_str = response_data["timestamp"]

    # Parse the timestamp and verify it's UTC
    parsed_timestamp = datetime.fromisoformat(timestamp_str)
    assert parsed_timestamp.tzinfo is not None, "Timestamp should be timezone-aware"
    assert parsed_timestamp.tzinfo == timezone.utc, f"Expected UTC timezone, got {parsed_timestamp.tzinfo}"

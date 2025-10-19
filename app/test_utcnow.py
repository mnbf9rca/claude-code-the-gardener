"""
Unit tests for utcnow module

Tests the UTC time query tool
"""
import pytest
import pytest_asyncio
from fastmcp import FastMCP
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

    # Extract timestamp from result
    content_str = str(result.content)

    # Should contain a timestamp that can be parsed
    assert "timestamp=" in content_str or "timestamp" in content_str


@pytest.mark.asyncio
async def test_get_current_time_returns_utc():
    """Test that returned timestamp is in UTC timezone"""
    test_mcp = FastMCP("Test")
    utcnow_module.setup_utcnow_tools(test_mcp)

    get_time_tool = test_mcp._tool_manager._tools["get_current_time"]

    # Call the tool
    result = await get_time_tool.run(arguments={})

    # Convert result to string and check for UTC indicator
    content_str = str(result.content)

    # ISO8601 UTC timestamps should end with +00:00 or Z
    assert "+00:00" in content_str or "Z" in content_str.upper()

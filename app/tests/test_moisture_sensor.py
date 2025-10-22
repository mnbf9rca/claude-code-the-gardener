"""
Unit tests for moisture_sensor module with ESP32 HTTP integration

These test the moisture sensor functions with mocked HTTP responses
"""
import os
import pytest
import pytest_asyncio
from fastmcp import FastMCP
from utils.shared_state import reset_cycle, current_cycle_status

# Set ESP32_HOST before importing module (required)
os.environ["ESP32_HOST"] = "192.168.1.100"
os.environ["ESP32_PORT"] = "80"

import tools.moisture_sensor as ms_module


@pytest_asyncio.fixture(autouse=True)
async def reset_state():
    """Reset state before each test"""
    reset_cycle()
    ms_module.sensor_history.clear()
    yield


@pytest.mark.asyncio
async def test_read_moisture_success(httpx_mock):
    """Test successful moisture reading from ESP32"""
    # Mock ESP32 response
    httpx_mock.add_response(
        url="http://192.168.1.100:80/moisture",
        method="GET",
        json={"value": 2047, "timestamp": "2025-01-23T14:30:00Z", "status": "ok"}
    )

    test_mcp = FastMCP("Test")
    ms_module.setup_moisture_sensor_tools(test_mcp)
    read_tool = test_mcp._tool_manager._tools["read_moisture"]

    # Read moisture
    result = await read_tool.run(arguments={})
    assert result.content is not None

    # Check history was updated
    assert len(ms_module.sensor_history) == 1
    assert ms_module.sensor_history[0]["value"] == 2047


@pytest.mark.asyncio
async def test_read_moisture_timeout(httpx_mock):
    """Test moisture reading with ESP32 timeout"""
    # Mock timeout response
    httpx_mock.add_exception(
        Exception("Connection timeout"),
        url="http://192.168.1.100:80/moisture"
    )

    test_mcp = FastMCP("Test")
    ms_module.setup_moisture_sensor_tools(test_mcp)
    read_tool = test_mcp._tool_manager._tools["read_moisture"]

    # Should handle timeout gracefully
    result = await read_tool.run(arguments={})
    # FastMCP wraps errors, check that result indicates error
    assert "error" in result.content[0].text.lower() or "timeout" in result.content[0].text.lower()


@pytest.mark.asyncio
async def test_read_moisture_http_error(httpx_mock):
    """Test moisture reading with ESP32 HTTP error"""
    # Mock HTTP 500 error
    httpx_mock.add_response(
        url="http://192.168.1.100:80/moisture",
        status_code=500,
        text="Internal Server Error"
    )

    test_mcp = FastMCP("Test")
    ms_module.setup_moisture_sensor_tools(test_mcp)
    read_tool = test_mcp._tool_manager._tools["read_moisture"]

    # Should handle HTTP error gracefully
    result = await read_tool.run(arguments={})
    assert "error" in result.content[0].text.lower() or "500" in result.content[0].text.lower()


@pytest.mark.asyncio
async def test_read_moisture_invalid_json(httpx_mock):
    """Test moisture reading with invalid JSON response"""
    # Mock invalid JSON
    httpx_mock.add_response(
        url="http://192.168.1.100:80/moisture",
        text="not json"
    )

    test_mcp = FastMCP("Test")
    ms_module.setup_moisture_sensor_tools(test_mcp)
    read_tool = test_mcp._tool_manager._tools["read_moisture"]

    # Should handle invalid JSON gracefully
    result = await read_tool.run(arguments={})
    assert "error" in result.content[0].text.lower()


@pytest.mark.asyncio
async def test_sensor_history_limit(httpx_mock):
    """Test that sensor history is limited to prevent memory issues"""
    # Mock ESP32 response
    httpx_mock.add_response(
        url="http://192.168.1.100:80/moisture",
        method="GET",
        json={"value": 3000, "timestamp": "2025-01-23T14:30:00Z", "status": "ok"}
    )

    test_mcp = FastMCP("Test")
    ms_module.setup_moisture_sensor_tools(test_mcp)
    read_tool = test_mcp._tool_manager._tools["read_moisture"]

    # Add 1440 entries directly first
    for i in range(1440):
        ms_module.sensor_history.append({
            "value": 2000 + i,
            "timestamp": f"2024-01-01T{i//60:02d}:{i%60:02d}:00"
        })

    # Now read one more through the tool - it should keep at 1440
    await read_tool.run(arguments={})

    # Should be capped at 1440 (oldest removed, newest added)
    assert len(ms_module.sensor_history) == 1440


@pytest.mark.asyncio
async def test_sensor_history_sampling():
    """Test that history sampling works correctly"""
    test_mcp = FastMCP("Test")
    ms_module.setup_moisture_sensor_tools(test_mcp)
    history_tool = test_mcp._tool_manager._tools["get_moisture_history"]

    # Add exactly 60 entries (1 hour of data)
    for i in range(60):
        ms_module.sensor_history.append({
            "value": 2000 + i,
            "timestamp": f"2024-01-01T00:{i:02d}:00"
        })

    # Request 1 hour of history (should get 6 samples - every 10 min)
    result = await history_tool.run(arguments={"hours": 1})
    # Result is in tool format, verify it executed without error
    assert result.content is not None


@pytest.mark.asyncio
async def test_history_sampling_with_more_data_than_needed():
    """Test sampling when we have more data points than requested"""
    test_mcp = FastMCP("Test")
    ms_module.setup_moisture_sensor_tools(test_mcp)
    history_tool = test_mcp._tool_manager._tools["get_moisture_history"]

    # Add 120 entries (2 hours of data)
    for i in range(120):
        ms_module.sensor_history.append({
            "value": 2000 + i,
            "timestamp": f"2024-01-01T{i//60:02d}:{i%60:02d}:00"
        })

    # Request only 1 hour (should sample from all 120 to get 6 points)
    result = await history_tool.run(arguments={"hours": 1})
    # The sampling should pick evenly distributed points
    assert result.content is not None


@pytest.mark.asyncio
async def test_read_moisture_uses_esp32_timestamp(httpx_mock):
    """Test that moisture reading uses ESP32's NTP-synced timestamp"""
    # Mock ESP32 response with real ISO8601 timestamp
    httpx_mock.add_response(
        url="http://192.168.1.100:80/moisture",
        json={
            "value": 2500,
            "timestamp": "2025-01-23T18:45:30Z",
            "status": "ok"
        }
    )

    test_mcp = FastMCP("Test")
    ms_module.setup_moisture_sensor_tools(test_mcp)
    read_tool = test_mcp._tool_manager._tools["read_moisture"]

    await read_tool.run(arguments={})

    # Verify ESP32's timestamp was stored
    assert len(ms_module.sensor_history) == 1
    assert ms_module.sensor_history[0]["timestamp"] == "2025-01-23T18:45:30Z"

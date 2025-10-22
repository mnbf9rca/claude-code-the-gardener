"""
Unit tests for moisture_sensor module with ESP32 HTTP integration

These test the moisture sensor functions with mocked HTTP responses
"""
from dotenv import load_dotenv

# Load environment variables from .env file BEFORE importing modules
load_dotenv()

import os
import pytest
import pytest_asyncio
import httpx
from fastmcp import FastMCP
from utils.shared_state import reset_cycle, current_cycle_status
import tools.moisture_sensor as ms_module

# Ensure required env vars are set (will use .env values, or use test defaults)
os.environ.setdefault("ESP32_HOST", "192.168.1.100")
os.environ.setdefault("ESP32_PORT", "80")


@pytest.fixture
def esp32_base_url():
    """Get ESP32 base URL for mocking"""
    from utils.esp32_config import get_esp32_config
    return get_esp32_config().base_url


@pytest_asyncio.fixture(autouse=True)
async def reset_state():
    """Reset state before each test"""
    reset_cycle()
    ms_module.sensor_history.clear()

    # Reset ESP32 config singleton
    import utils.esp32_config
    utils.esp32_config._config = None

    yield

    # Clean up singleton after test
    utils.esp32_config._config = None


@pytest.mark.asyncio
async def test_read_moisture_success(httpx_mock, esp32_base_url):
    """Test successful moisture reading from ESP32"""
    # Mock ESP32 response
    httpx_mock.add_response(
        url=f"{esp32_base_url}/moisture",
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
async def test_read_moisture_timeout(httpx_mock, esp32_base_url):
    """Test moisture reading with ESP32 timeout"""
    # Mock timeout response using httpx.TimeoutException
    httpx_mock.add_exception(
        httpx.TimeoutException("Connection timeout"),
        url=f"{esp32_base_url}/moisture"
    )

    test_mcp = FastMCP("Test")
    ms_module.setup_moisture_sensor_tools(test_mcp)
    read_tool = test_mcp._tool_manager._tools["read_moisture"]

    # Should raise ValueError with timeout message
    with pytest.raises(ValueError, match="timeout"):
        await read_tool.run(arguments={})


@pytest.mark.asyncio
async def test_read_moisture_http_error(httpx_mock, esp32_base_url):
    """Test moisture reading with ESP32 HTTP error"""
    # Mock HTTP 500 error
    httpx_mock.add_response(
        url=f"{esp32_base_url}/moisture",
        status_code=500,
        text="Internal Server Error"
    )

    test_mcp = FastMCP("Test")
    ms_module.setup_moisture_sensor_tools(test_mcp)
    read_tool = test_mcp._tool_manager._tools["read_moisture"]

    # Should raise ValueError with HTTP error
    with pytest.raises(ValueError, match="500|HTTP error"):
        await read_tool.run(arguments={})


@pytest.mark.asyncio
async def test_read_moisture_invalid_json(httpx_mock, esp32_base_url):
    """Test moisture reading with invalid JSON response"""
    # Mock invalid JSON
    httpx_mock.add_response(
        url=f"{esp32_base_url}/moisture",
        text="not json"
    )

    test_mcp = FastMCP("Test")
    ms_module.setup_moisture_sensor_tools(test_mcp)
    read_tool = test_mcp._tool_manager._tools["read_moisture"]

    # Should raise ValueError with JSON error
    with pytest.raises(ValueError):
        await read_tool.run(arguments={})


@pytest.mark.asyncio
async def test_sensor_history_limit(httpx_mock, esp32_base_url):
    """Test that sensor history is limited to prevent memory issues"""
    # Mock ESP32 response
    httpx_mock.add_response(
        url=f"{esp32_base_url}/moisture",
        method="GET",
        json={"value": 3000, "timestamp": "2025-01-23T14:30:00Z", "status": "ok"}
    )

    test_mcp = FastMCP("Test")
    ms_module.setup_moisture_sensor_tools(test_mcp)
    read_tool = test_mcp._tool_manager._tools["read_moisture"]

    # Add MAX_SENSOR_HISTORY_LENGTH entries directly first
    for i in range(ms_module.MAX_SENSOR_HISTORY_LENGTH):
        ms_module.sensor_history.append({
            "value": 2000 + i,
            "timestamp": f"2024-01-01T{i//60:02d}:{i%60:02d}:00"
        })

    # Now read one more through the tool - it should keep at max length
    await read_tool.run(arguments={})

    # Verify sensor_history does not exceed the maximum allowed length
    assert len(ms_module.sensor_history) <= ms_module.MAX_SENSOR_HISTORY_LENGTH
    # Should be capped at MAX_SENSOR_HISTORY_LENGTH (oldest removed, newest added)
    assert len(ms_module.sensor_history) == ms_module.MAX_SENSOR_HISTORY_LENGTH


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
async def test_read_moisture_uses_esp32_timestamp(httpx_mock, esp32_base_url):
    """Test that moisture reading uses ESP32's NTP-synced timestamp"""
    # Mock ESP32 response with real ISO8601 timestamp
    httpx_mock.add_response(
        url=f"{esp32_base_url}/moisture",
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

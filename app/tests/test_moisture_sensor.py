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

    # Clear history and delete disk file to ensure clean state
    ms_module.sensor_history.clear()
    if ms_module.sensor_history.file_path.exists():
        ms_module.sensor_history.file_path.unlink()

    # Reset ESP32 config singleton
    import utils.esp32_config
    utils.esp32_config._config = None

    yield

    # Clean up disk file and singleton after test
    if ms_module.sensor_history.file_path.exists():
        ms_module.sensor_history.file_path.unlink()
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

    # Check history was updated (JsonlHistory)
    all_readings = ms_module.sensor_history.get_all()
    assert len(all_readings) == 1
    assert all_readings[0]["value"] == 2047


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
async def test_sensor_history_sampling():
    """Test that history sampling works correctly"""
    from freezegun import freeze_time
    from datetime import datetime, timezone, timedelta

    test_mcp = FastMCP("Test")
    ms_module.setup_moisture_sensor_tools(test_mcp)
    history_tool = test_mcp._tool_manager._tools["get_moisture_history"]

    with freeze_time("2024-01-01 01:00:00"):
        # Add exactly 60 entries (1 hour of data) - all within last hour
        base_time = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        for i in range(60):
            ms_module.sensor_history.append({
                "value": 2000 + i,
                "timestamp": (base_time + timedelta(minutes=i)).isoformat()
            })

        # Request 1 hour of history (should get samples with time-bucketing)
        result = await history_tool.run(arguments={"hours": 1})
        # Result is in tool format, verify it executed without error
        assert result.content is not None


@pytest.mark.asyncio
async def test_history_sampling_with_more_data_than_needed():
    """Test sampling when we have more data points than requested"""
    from freezegun import freeze_time
    from datetime import datetime, timezone, timedelta

    test_mcp = FastMCP("Test")
    ms_module.setup_moisture_sensor_tools(test_mcp)
    history_tool = test_mcp._tool_manager._tools["get_moisture_history"]

    with freeze_time("2024-01-01 02:00:00"):
        # Add 120 entries (2 hours of data) - all within last 2 hours
        base_time = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        for i in range(120):
            ms_module.sensor_history.append({
                "value": 2000 + i,
                "timestamp": (base_time + timedelta(minutes=i)).isoformat()
            })

        # Request only 1 hour - should filter to last hour, then sample
        result = await history_tool.run(arguments={"hours": 1})
        # The sampling should pick evenly distributed points from last hour
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

    # Verify ESP32's timestamp was stored (JsonlHistory)
    all_readings = ms_module.sensor_history.get_all()
    assert len(all_readings) == 1
    assert all_readings[0]["timestamp"] == "2025-01-23T18:45:30Z"


@pytest.mark.asyncio
async def test_moisture_history_respects_time_window():
    """Test that get_moisture_history actually filters by time window"""
    from freezegun import freeze_time
    from datetime import datetime, timezone, timedelta

    test_mcp = FastMCP("Test")
    ms_module.setup_moisture_sensor_tools(test_mcp)
    history_tool = test_mcp._tool_manager._tools["get_moisture_history"]

    # Use freezegun to fix current time
    with freeze_time("2025-01-24 12:00:00"):
        # Add old data (25 hours ago - outside 24h window)
        old_time = datetime(2025, 1, 23, 11, 0, 0, tzinfo=timezone.utc)
        for i in range(10):
            ms_module.sensor_history.append({
                "timestamp": (old_time + timedelta(minutes=i)).isoformat(),
                "value": 1000 + i
            })

        # Add recent data (within last hour)
        recent_time = datetime(2025, 1, 24, 11, 0, 0, tzinfo=timezone.utc)
        for i in range(10):
            ms_module.sensor_history.append({
                "timestamp": (recent_time + timedelta(minutes=i)).isoformat(),
                "value": 2000 + i
            })

        # Request last 1 hour - should only get recent data
        result = await history_tool.run(arguments={"hours": 1})
        # Result is in tool format, extract content
        import json
        readings = json.loads(result.content[0].text)

        # Should have some results (the recent data)
        assert len(readings) > 0

        # All returned timestamps should be within last hour
        for timestamp, value in readings:
            dt = datetime.fromisoformat(timestamp)
            age_hours = (datetime(2025, 1, 24, 12, 0, 0, tzinfo=timezone.utc) - dt).total_seconds() / 3600
            assert age_hours <= 1.0, f"Reading at {timestamp} is older than 1 hour"

        # All returned values should be from recent data (2000-2010 range)
        for timestamp, value in readings:
            assert 2000 <= value < 2010, f"Got value {value}, expected 2000-2010 (recent data)"

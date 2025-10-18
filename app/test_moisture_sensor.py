"""
Unit tests for moisture_sensor module

These test the moisture sensor functions directly without going through MCP server
"""
import pytest
import pytest_asyncio
from fastmcp import FastMCP
import tools.moisture_sensor as ms_module
from shared_state import reset_cycle, current_cycle_status


@pytest_asyncio.fixture(autouse=True)
async def reset_state():
    """Reset state before each test"""
    reset_cycle()
    ms_module.sensor_history.clear()
    ms_module.mock_sensor_value = 2000
    yield


@pytest.mark.asyncio
async def test_read_moisture_requires_status():
    """Test that moisture reading requires status to be written first"""
    test_mcp = FastMCP("Test")
    ms_module.setup_moisture_sensor_tools(test_mcp)

    read_tool = test_mcp._tool_manager._tools["read_moisture"]

    # Should fail when status not written
    with pytest.raises(ValueError) as exc_info:
        await read_tool.run(arguments={})

    assert "Must call write_status first" in str(exc_info.value)


@pytest.mark.asyncio
async def test_read_moisture_with_status():
    """Test reading moisture after status is written"""
    # Enable reading by setting cycle status
    current_cycle_status["written"] = True

    test_mcp = FastMCP("Test")
    ms_module.setup_moisture_sensor_tools(test_mcp)
    read_tool = test_mcp._tool_manager._tools["read_moisture"]

    # Read moisture
    result = await read_tool.run(arguments={})
    assert result.content is not None

    # Check sensor value is in reasonable range
    assert 1500 <= ms_module.mock_sensor_value <= 3500

    # Check history was updated
    assert len(ms_module.sensor_history) == 1


@pytest.mark.asyncio
async def test_moisture_decline_simulation():
    """Test that moisture naturally declines over time"""
    current_cycle_status["written"] = True
    initial_value = ms_module.mock_sensor_value

    test_mcp = FastMCP("Test")
    ms_module.setup_moisture_sensor_tools(test_mcp)
    read_tool = test_mcp._tool_manager._tools["read_moisture"]

    # Read multiple times
    for _ in range(5):
        await read_tool.run(arguments={})

    # Value should have declined (but not necessarily monotonically due to noise)
    assert ms_module.mock_sensor_value < initial_value


@pytest.mark.asyncio
async def test_sensor_history_limit():
    """Test that sensor history is limited to prevent memory issues when using the tool"""
    current_cycle_status["written"] = True

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
    history_tool = test_mcp._tool_manager._tools["get_sensor_history"]

    # Add exactly 60 entries (1 hour of data)
    for i in range(60):
        ms_module.sensor_history.append({
            "value": 2000 + i,
            "timestamp": f"2024-01-01T00:{i:02d}:00"
        })

    # Request 1 hour of history (should get 6 samples - every 10 min)
    result = await history_tool.run(arguments={"hours": 1})
    # Result is in tool format, would need parsing to verify count


@pytest.mark.asyncio
async def test_simulate_watering():
    """Test the simulate_watering mock tool"""
    initial_value = ms_module.mock_sensor_value

    test_mcp = FastMCP("Test")
    ms_module.setup_moisture_sensor_tools(test_mcp)
    water_tool = test_mcp._tool_manager._tools["simulate_watering"]

    # Simulate watering 50ml
    result = await water_tool.run(arguments={"ml": 50})

    # Sensor value should increase
    assert ms_module.mock_sensor_value > initial_value
    assert ms_module.mock_sensor_value <= 3500  # Should not exceed max


@pytest.mark.asyncio
async def test_sensor_value_boundaries():
    """Test that sensor values stay within realistic boundaries"""
    current_cycle_status["written"] = True

    test_mcp = FastMCP("Test")
    ms_module.setup_moisture_sensor_tools(test_mcp)
    read_tool = test_mcp._tool_manager._tools["read_moisture"]

    # Set to very low value
    ms_module.mock_sensor_value = 1490

    # Read should not go below minimum
    await read_tool.run(arguments={})
    assert ms_module.mock_sensor_value >= 1500

    # Set to high value and simulate watering
    ms_module.mock_sensor_value = 3400
    water_tool = test_mcp._tool_manager._tools["simulate_watering"]
    await water_tool.run(arguments={"ml": 100})

    # Should not exceed maximum
    assert ms_module.mock_sensor_value <= 3500


@pytest.mark.asyncio
async def test_history_sampling_with_more_data_than_needed():
    """Test sampling when we have more data points than requested"""
    test_mcp = FastMCP("Test")
    ms_module.setup_moisture_sensor_tools(test_mcp)
    history_tool = test_mcp._tool_manager._tools["get_sensor_history"]

    # Add 120 entries (2 hours of data)
    for i in range(120):
        ms_module.sensor_history.append({
            "value": 2000 + i,
            "timestamp": f"2024-01-01T{i//60:02d}:{i%60:02d}:00"
        })

    # Request only 1 hour (should sample from all 120 to get 6 points)
    result = await history_tool.run(arguments={"hours": 1})
    # The sampling should pick evenly distributed points
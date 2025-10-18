"""
Integration Tests for Plant Care MCP Server

These tests verify the complete MCP server functionality with all components
working together. They test through the MCP server interface, not individual modules.

For unit tests of individual modules, see:
- test_plant_status.py - Unit tests for plant status module
- test_moisture_sensor.py - Unit tests for moisture sensor module
- test_water_pump.py - Unit tests for water pump module
- test_light.py - Unit tests for light control module
- test_camera.py - Unit tests for camera module
"""
import pytest
import pytest_asyncio
import json
from datetime import datetime, timedelta
from freezegun import freeze_time
from server import mcp
from shared_state import reset_cycle
import tools.plant_status as ps_module
import tools.moisture_sensor as ms_module
import tools.water_pump as wp_module
import tools.light as light_module
import tools.camera as camera_module


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

    # Reset water pump history
    wp_module.water_history.clear()

    # Reset light state
    light_module.light_state["status"] = "off"
    light_module.light_state["last_on"] = None
    light_module.light_state["last_off"] = None
    light_module.light_state["scheduled_off"] = None

    # Reset camera history
    camera_module.photo_history.clear()

    yield
    # Teardown if needed (currently no cleanup required)


@pytest.mark.asyncio
async def test_server_initialization():
    """Test that the server initializes with expected tools"""
    # Get list of available tools - FastMCP v2 uses _tools (private attr)
    tools = [tool.name for tool in mcp._tool_manager._tools.values()]

    # Check that all tools are present
    # Plant status tools
    assert "write_status" in tools
    assert "get_current_status" in tools
    assert "get_status_history" in tools

    # Moisture sensor tools
    assert "read_moisture" in tools
    assert "get_sensor_history" in tools
    assert "simulate_watering" in tools

    # Water pump tools
    assert "dispense" in tools
    assert "get_usage_24h" in tools

    # Light tools
    assert "turn_on" in tools
    assert "get_light_status" in tools

    # Camera tools
    assert "capture" in tools
    assert "get_recent_photos" in tools

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


@pytest.mark.asyncio
async def test_water_pump_integration():
    """Test water pump integration with gatekeeper and moisture sensor"""
    # Try to dispense water before writing status - should fail
    dispense_tool = mcp._tool_manager._tools["dispense"]
    with pytest.raises(ValueError, match="Must call write_status first"):
        await dispense_tool.run(arguments={"ml": 50})

    # Write status first
    write_status_tool = mcp._tool_manager._tools["write_status"]
    await write_status_tool.run(arguments={
        "sensor_reading": 1800,
        "water_24h": 0,
        "light_today": 0,
        "plant_state": "healthy",
        "next_action_sequence": [{"order": 1, "action": "water", "value": 50}],
        "reasoning": "Testing water pump"
    })

    # Now dispense water should work
    initial_moisture = ms_module.mock_sensor_value
    tool_result = await dispense_tool.run(arguments={"ml": 50})
    result = json.loads(tool_result.content[0].text)

    assert result["dispensed"] == 50
    assert result["remaining_24h"] == 450
    # Check moisture sensor was updated
    assert ms_module.mock_sensor_value > initial_moisture
    print("✓ Water pump integration works with gatekeeper and sensor update")


@pytest.mark.asyncio
async def test_light_integration():
    """Test light control integration with gatekeeper"""
    # Try to turn on light before writing status - should fail
    turn_on_tool = mcp._tool_manager._tools["turn_on"]
    with pytest.raises(ValueError, match="Must call write_status first"):
        await turn_on_tool.run(arguments={"minutes": 60})

    # Write status first
    write_status_tool = mcp._tool_manager._tools["write_status"]
    await write_status_tool.run(arguments={
        "sensor_reading": 2000,
        "water_24h": 0,
        "light_today": 0,
        "plant_state": "healthy",
        "next_action_sequence": [{"order": 1, "action": "light", "value": 60}],
        "reasoning": "Testing light control"
    })

    # Now turn on light should work
    tool_result = await turn_on_tool.run(arguments={"minutes": 60})
    result = json.loads(tool_result.content[0].text)

    assert result["status"] == "on"
    assert result["duration_minutes"] == 60
    assert "off_at" in result

    # Check light status
    status_tool = mcp._tool_manager._tools["get_light_status"]
    tool_result = await status_tool.run(arguments={})
    status = json.loads(tool_result.content[0].text)
    assert status["status"] == "on"
    assert status["can_activate"] is False
    print("✓ Light control integration works with gatekeeper")


@pytest.mark.asyncio
async def test_camera_integration():
    """Test camera integration with gatekeeper"""
    # Try to capture before writing status - should fail
    capture_tool = mcp._tool_manager._tools["capture"]
    with pytest.raises(ValueError, match="Must call write_status first"):
        await capture_tool.run(arguments={})

    # Write status first
    write_status_tool = mcp._tool_manager._tools["write_status"]
    await write_status_tool.run(arguments={
        "sensor_reading": 2000,
        "water_24h": 0,
        "light_today": 0,
        "plant_state": "healthy",
        "next_action_sequence": [{"order": 1, "action": "observe", "value": None}],
        "reasoning": "Testing camera"
    })

    # Now capture should work
    tool_result = await capture_tool.run(arguments={})
    result = json.loads(tool_result.content[0].text)

    assert "url" in result
    assert result["url"].startswith("http://192.168.1.100/photos/")
    assert "timestamp" in result

    # Check recent photos
    recent_tool = mcp._tool_manager._tools["get_recent_photos"]
    tool_result = await recent_tool.run(arguments={"limit": 5})
    photos = json.loads(tool_result.content[0].text)
    assert len(photos) == 1
    assert photos[0]["url"] == result["url"]
    print("✓ Camera integration works with gatekeeper and history")


@pytest.mark.asyncio
async def test_full_cycle_integration():
    """Test a complete plant care cycle with all tools"""
    # 1. Write initial status
    write_status_tool = mcp._tool_manager._tools["write_status"]
    await write_status_tool.run(arguments={
        "sensor_reading": 1600,  # Dry
        "water_24h": 100,
        "light_today": 60,
        "plant_state": "stressed",
        "next_action_sequence": [
            {"order": 1, "action": "water", "value": 80},
            {"order": 2, "action": "light", "value": 90},
            {"order": 3, "action": "observe", "value": None}
        ],
        "reasoning": "Plant needs water and light"
    })

    # 2. Read moisture (should be dry)
    moisture_tool = mcp._tool_manager._tools["read_moisture"]
    tool_result = await moisture_tool.run(arguments={})
    moisture = json.loads(tool_result.content[0].text)
    assert moisture["value"] < 2000  # Dry

    # 3. Dispense water
    dispense_tool = mcp._tool_manager._tools["dispense"]
    tool_result = await dispense_tool.run(arguments={"ml": 80})
    water = json.loads(tool_result.content[0].text)
    assert water["dispensed"] == 80

    # 4. Turn on light
    turn_on_tool = mcp._tool_manager._tools["turn_on"]
    tool_result = await turn_on_tool.run(arguments={"minutes": 90})
    light = json.loads(tool_result.content[0].text)
    assert light["status"] == "on"

    # 5. Take a photo
    capture_tool = mcp._tool_manager._tools["capture"]
    tool_result = await capture_tool.run(arguments={})
    photo = json.loads(tool_result.content[0].text)
    assert "url" in photo

    # 6. Check usage statistics
    usage_tool = mcp._tool_manager._tools["get_usage_24h"]
    tool_result = await usage_tool.run(arguments={})
    usage = json.loads(tool_result.content[0].text)
    assert usage["used_ml"] == 80
    assert usage["events"] == 1

    print("✓ Full plant care cycle integration successful")


@pytest.mark.asyncio
async def test_action_limits_with_time():
    """Test that time-based limits work correctly with freezegun"""
    # Write status first
    write_status_tool = mcp._tool_manager._tools["write_status"]
    await write_status_tool.run(arguments={
        "sensor_reading": 2000,
        "water_24h": 0,
        "light_today": 0,
        "plant_state": "healthy",
        "next_action_sequence": [],
        "reasoning": "Testing limits"
    })

    with freeze_time("2024-01-01 12:00:00") as frozen_time:
        # Dispense water up to limit
        dispense_tool = mcp._tool_manager._tools["dispense"]
        for _ in range(5):
            await dispense_tool.run(arguments={"ml": 100})

        # Should be at limit now
        usage_tool = mcp._tool_manager._tools["get_usage_24h"]
        tool_result = await usage_tool.run(arguments={})
        usage = json.loads(tool_result.content[0].text)
        assert usage["used_ml"] == 500
        assert usage["remaining_ml"] == 0

        # Move forward 25 hours
        frozen_time.move_to("2024-01-02 13:00:00")

        # Should be able to dispense again
        tool_result = await dispense_tool.run(arguments={"ml": 100})
        result = json.loads(tool_result.content[0].text)
        assert result["dispensed"] == 100

    print("✓ Time-based water limits work correctly with freezegun")


# Use pytest to run tests instead of custom runner
if __name__ == "__main__":
    # Run with: pytest test_server.py -v
    pytest.main([__file__, "-v"])
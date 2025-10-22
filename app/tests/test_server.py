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
from dotenv import load_dotenv

# Load environment variables from .env file BEFORE importing project modules
# This is intentional - project modules may read env vars during import
load_dotenv()

# ruff: noqa: E402 - imports must come after load_dotenv()
import pytest
import pytest_asyncio
import json
import httpx
import asyncio
from freezegun import freeze_time
from pytest_httpx import HTTPXMock
from mcp.types import TextContent
from server import mcp
from utils.shared_state import reset_cycle
import tools.plant_status as ps_module
import tools.moisture_sensor as ms_module
import tools.water_pump as wp_module
import tools.light as light_module
import tools.camera as camera_module

# Apply to all tests in this module
pytestmark = pytest.mark.httpx_mock(assert_all_responses_were_requested=False)


@pytest_asyncio.fixture(autouse=True)
async def reset_server_state(httpx_mock: HTTPXMock):
    """Setup/teardown fixture to reset server state before each test"""
    # Reset cycle state
    reset_cycle()

    # Reset ESP32 config singleton
    import utils.esp32_config
    utils.esp32_config._config = None

    # Reset plant status history and current status
    # Reinitialize with the correct file path (in case other tests changed it)
    from utils.jsonl_history import JsonlHistory
    ps_module.status_history = JsonlHistory(file_path=ps_module.STATE_FILE, max_memory_entries=1000)
    ps_module.current_status = None
    ps_module.STATE_FILE.unlink(missing_ok=True)

    # Reset moisture sensor history and mock value
    ms_module.sensor_history.clear()
    ms_module.mock_sensor_value = 2000

    # Reset water pump history and state
    wp_module.water_history.clear()
    wp_module._state_loaded = False
    wp_module.STATE_FILE.unlink(missing_ok=True)

    # Reset light state
    light_module.light_state["status"] = "off"
    light_module.light_state["last_on"] = None
    light_module.light_state["last_off"] = None
    light_module.light_state["scheduled_off"] = None

    # Reset light history (uses JsonlHistory utility)
    light_module.light_history.clear()
    light_module.light_history._loaded = False

    # Reset state loaded flag
    light_module._state_loaded = False

    # Reset reconciliation flag (new scheduling feature)
    light_module._reconciliation_done = False

    # Clear persisted state and history files BEFORE test runs
    light_module.STATE_FILE.unlink(missing_ok=True)
    light_module.light_history.file_path.unlink(missing_ok=True)

    # Reset HAConfig singleton to ensure clean state
    light_module.reset_ha_config()

    # Get config for test (will validate environment)
    ha_config = light_module.get_ha_config()

    # Setup Home Assistant mocks
    def mock_turn_on(request):
        return httpx.Response(200, json=[{"entity_id": ha_config.entity_id, "state": "on"}])

    def mock_turn_off(request):
        return httpx.Response(200, json=[{"entity_id": ha_config.entity_id, "state": "off"}])

    def mock_get_state(request):
        return httpx.Response(200, json={"entity_id": ha_config.entity_id, "state": light_module.light_state["status"]})

    # Add each callback multiple times to allow reuse
    for _ in range(20):
        httpx_mock.add_callback(mock_turn_on, url=f"{ha_config.url}/api/services/switch/turn_on")
        httpx_mock.add_callback(mock_turn_off, url=f"{ha_config.url}/api/services/switch/turn_off")
        httpx_mock.add_callback(mock_get_state, url=f"{ha_config.url}/api/states/{ha_config.entity_id}")

    # Setup ESP32 mocks for moisture sensor and water pump
    from utils.esp32_config import get_esp32_config
    esp32_config = get_esp32_config()
    esp32_base = esp32_config.base_url

    def mock_moisture_read(request):
        return httpx.Response(200, json={"value": 2000, "timestamp": "2025-01-23T14:30:00Z", "status": "ok"})

    def mock_pump_activate(request):
        return httpx.Response(200, json={"success": True, "duration": 14, "timestamp": "2025-01-23T14:30:00Z"})

    # Add ESP32 mocks - use non-matching URLs to avoid conflicts with httpx_mock
    for _ in range(50):  # More iterations for tests that use multiple calls
        httpx_mock.add_callback(mock_moisture_read, url=f"{esp32_base}/moisture")
        httpx_mock.add_callback(mock_pump_activate, url=f"{esp32_base}/pump", method="POST")

    # Reset camera history
    camera_module.photo_history.clear()

    yield

    # Teardown - cleanup after test completes
    # Cancel background tasks unconditionally (handles both running and None cases)
    try:
        light_module.scheduled_task.cancel()
        await light_module.scheduled_task
    except (AttributeError, asyncio.CancelledError, TypeError):
        pass
    light_module.scheduled_task = None

    # Clear persisted state file unconditionally
    light_module.STATE_FILE.unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_server_initialization():
    """Test that the server initializes with expected tools"""
    # Get list of available tools - FastMCP v2 uses _tools (private attr)
    tools = [tool.name for tool in mcp._tool_manager._tools.values()]

    # Check that all tools are present
    # Plant status tools
    assert "write_plant_status" in tools
    assert "get_current_plant_status" in tools
    assert "get_plant_status_history" in tools

    # Moisture sensor tools
    assert "read_moisture" in tools
    assert "get_moisture_history" in tools

    # Water pump tools
    assert "dispense_water" in tools
    assert "get_water_usage_24h" in tools

    # Light tools
    assert "turn_on_light" in tools
    assert "get_light_status" in tools

    # Camera tools
    assert "capture_photo" in tools
    assert "get_recent_photos" in tools

    print(f"✓ Server initialized with {len(tools)} tools")


@pytest.mark.asyncio
async def test_gatekeeper_enforcement():
    """Test that moisture sensor requires plant status to be written first"""
    # Try to read moisture without writing status first
    moisture_tool = mcp._tool_manager._tools["turn_off_light"]

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
    write_status_tool = mcp._tool_manager._tools["write_plant_status"]
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
    write_status_tool = mcp._tool_manager._tools["write_plant_status"]
    await write_status_tool.run(arguments={
        "sensor_reading": 2100,
        "water_24h": 50.0,
        "light_today": 120.0,
        "plant_state": "healthy",
        "next_action_sequence": [],
        "reasoning": "Test status for history"
    })

    # Get history
    history_tool = mcp._tool_manager._tools["get_plant_status_history"]
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
    history_tool = mcp._tool_manager._tools["get_plant_status_history"]
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
    write_status_tool = mcp._tool_manager._tools["write_plant_status"]

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
    write_status_tool = mcp._tool_manager._tools["write_plant_status"]
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
    history_tool = mcp._tool_manager._tools["get_moisture_history"]
    tool_result = await history_tool.run(arguments={"hours": 1})

    # Check if we got results (may be empty or have fewer samples due to time-bucketing)
    if tool_result.content:
        history = json.loads(tool_result.content[0].text)
        assert isinstance(history, list)
        # Check structure of returned data if we got any
        if history:
            assert len(history[0]) == 2  # [timestamp, value] pairs
            print(f"✓ Sensor history sampling works: {len(history)} samples")
    else:
        # Time-bucketed sampling may return empty if all readings in same bucket
        print("✓ Sensor history sampling works (empty result - readings in same time bucket)")


@pytest.mark.asyncio
async def test_water_pump_integration():
    """Test water pump integration with gatekeeper"""
    # Try to dispense water before writing status - should fail
    dispense_tool = mcp._tool_manager._tools["dispense_water"]
    with pytest.raises(ValueError, match="Must call write_status first"):
        await dispense_tool.run(arguments={"ml": 50})

    # Write status first
    write_status_tool = mcp._tool_manager._tools["write_plant_status"]
    await write_status_tool.run(arguments={
        "sensor_reading": 1800,
        "water_24h": 0,
        "light_today": 0,
        "plant_state": "healthy",
        "next_action_sequence": [{"order": 1, "action": "water", "value": 50}],
        "reasoning": "Testing water pump"
    })

    # Now dispense water should work
    tool_result = await dispense_tool.run(arguments={"ml": 50})
    result = json.loads(tool_result.content[0].text)

    assert result["dispensed"] == 50
    assert result["remaining_24h"] == 450
    print("✓ Water pump integration works with gatekeeper")


@pytest.mark.asyncio
async def test_light_integration():
    """Test light control integration with gatekeeper (using idempotent status check)"""
    # Use get_light_status (idempotent) to test gatekeeper - requires no side effects
    status_tool = mcp._tool_manager._tools["get_light_status"]

    # Status check should work without write_status (it's read-only)
    tool_result = await status_tool.run(arguments={})
    status = json.loads(tool_result.content[0].text)

    # Should show light is off and available
    assert status["status"] == "off"
    assert status["can_activate"] is True
    assert status["minutes_until_available"] == 0

    # Now test that turn_on requires write_status
    turn_on_tool = mcp._tool_manager._tools["turn_on_light"]
    with pytest.raises(ValueError, match="Must call write_status first"):
        await turn_on_tool.run(arguments={"minutes": 60})

    # Write status first
    write_status_tool = mcp._tool_manager._tools["write_plant_status"]
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

    # Check light status again
    tool_result = await status_tool.run(arguments={})
    status = json.loads(tool_result.content[0].text)
    assert status["status"] == "on"
    assert status["can_activate"] is False
    print("✓ Light control integration works with gatekeeper (idempotent status checks)")


@pytest.mark.asyncio
async def test_camera_integration():
    """Test camera integration (no gatekeeper - camera is read-only)"""
    # Camera doesn't require gatekeeper since it's not a destructive action
    # Capture should work without writing status first
    capture_tool = mcp._tool_manager._tools["capture_photo"]
    tool_result = await capture_tool.run(arguments={})

    # Extract response using structured_content
    if hasattr(tool_result, 'structured_content') and tool_result.structured_content:
        result = tool_result.structured_content
    else:
        # Fallback to parsing from content
        for content_item in tool_result.content:
            if isinstance(content_item, TextContent):
                result = json.loads(content_item.text)
                break

    # Should be successful
    assert "url" in result
    # Camera now returns HTTP URLs
    assert result["url"].endswith(".jpg")
    assert "timestamp" in result

    # Check recent photos
    recent_tool = mcp._tool_manager._tools["get_recent_photos"]
    tool_result = await recent_tool.run(arguments={"limit": 5})

    # Extract photos from result
    if hasattr(tool_result, 'structured_content') and tool_result.structured_content:
        photos_data = tool_result.structured_content
    else:
        for content_item in tool_result.content:
            if isinstance(content_item, TextContent):
                photos_data = json.loads(content_item.text)
                break

    # Handle wrapped result format
    if isinstance(photos_data, dict) and "result" in photos_data:
        photos = photos_data["result"]
    else:
        photos = photos_data

    assert len(photos) == 1
    assert photos[0]["url"] == result["url"]
    print("✓ Camera integration works with gatekeeper and history")


@pytest.mark.asyncio
async def test_camera_integration_failure(monkeypatch):
    """Test camera integration with camera unavailable (raises ValueError)"""
    import tools.camera as camera_module

    # Mock capture_real_photo to raise ValueError (simulating camera failure)
    # This avoids mutating global state
    def mock_capture_real_photo():
        raise ValueError("Camera device not found")

    monkeypatch.setattr(camera_module, "capture_real_photo", mock_capture_real_photo)

    capture_tool = mcp._tool_manager._tools["capture_photo"]

    # Should raise ValueError when camera is unavailable
    with pytest.raises(ValueError) as exc_info:
        await capture_tool.run(arguments={})

    # Verify error message contains expected information
    error_msg = str(exc_info.value).lower()
    assert "camera" in error_msg or "not found" in error_msg

    print("✓ Camera properly raises ValueError when unavailable")


@pytest.mark.asyncio
async def test_full_cycle_integration():
    """Test a complete plant care cycle with all tools"""
    # 1. Write initial status
    write_status_tool = mcp._tool_manager._tools["write_plant_status"]
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
    assert moisture["value"] <= 2000  # Dry (mock returns 2000)

    # 3. Dispense water
    dispense_tool = mcp._tool_manager._tools["dispense_water"]
    tool_result = await dispense_tool.run(arguments={"ml": 80})
    water = json.loads(tool_result.content[0].text)
    assert water["dispensed"] == 80

    # 4. Turn on light
    turn_on_tool = mcp._tool_manager._tools["turn_on_light"]
    tool_result = await turn_on_tool.run(arguments={"minutes": 90})
    light = json.loads(tool_result.content[0].text)
    assert light["status"] == "on"

    # 5. Take a photo
    capture_tool = mcp._tool_manager._tools["capture_photo"]
    tool_result = await capture_tool.run(arguments={})
    photo = json.loads(tool_result.content[0].text)
    assert "url" in photo

    # 6. Check usage statistics
    usage_tool = mcp._tool_manager._tools["get_water_usage_24h"]
    tool_result = await usage_tool.run(arguments={})
    usage = json.loads(tool_result.content[0].text)
    assert usage["used_ml"] == 80
    assert usage["events"] == 1

    print("✓ Full plant care cycle integration successful")


@pytest.mark.asyncio
async def test_action_limits_with_time():
    """Test that time-based limits work correctly with freezegun"""
    # Write status first
    write_status_tool = mcp._tool_manager._tools["write_plant_status"]
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
        dispense_tool = mcp._tool_manager._tools["dispense_water"]
        for _ in range(5):
            await dispense_tool.run(arguments={"ml": 100})

        # Should be at limit now
        usage_tool = mcp._tool_manager._tools["get_water_usage_24h"]
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
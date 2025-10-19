"""
Unit Tests for Water Pump Module

These tests verify the water pump functionality including:
- Dispensing water within limits
- 24-hour rolling limit enforcement
- Usage tracking and reporting
- State persistence and recovery
"""

import pytest
import pytest_asyncio
import json
from datetime import datetime, timedelta
from freezegun import freeze_time
from fastmcp import FastMCP
import tools.water_pump as wp_module
from tools.water_pump import setup_water_pump_tools
from shared_state import reset_cycle, current_cycle_status
from pathlib import Path


@pytest_asyncio.fixture(autouse=True)
async def setup_pump_state(tmp_path):
    """Reset water pump state before each test"""
    # Reset cycle state
    reset_cycle()
    current_cycle_status["written"] = True  # Allow tool calls

    # Use temp directory for state file (don't touch production state!)
    from utils.jsonl_history import JsonlHistory

    original_history = wp_module.water_history

    # Create new history instance with temp file
    wp_module.water_history = JsonlHistory(
        file_path=tmp_path / "water_pump_history.jsonl",
        max_memory_entries=1000
    )

    # Create MCP instance and setup tools
    mcp = FastMCP("test")
    setup_water_pump_tools(mcp)

    yield mcp

    # Restore original history
    wp_module.water_history = original_history


@pytest.mark.asyncio
async def test_dispense_basic(setup_pump_state):
    """Test basic water dispensing"""
    mcp = setup_pump_state
    dispense_tool = mcp._tool_manager._tools["dispense"]

    tool_result = await dispense_tool.run(arguments={"ml": 50})
    result = json.loads(tool_result.content[0].text)

    assert result["dispensed"] == 50
    assert result["remaining_24h"] == 450  # 500 - 50
    assert "timestamp" in result
    assert len(wp_module.water_history) == 1


@pytest.mark.asyncio
async def test_dispense_minimum_maximum(setup_pump_state):
    """Test min/max dispensing limits"""
    mcp = setup_pump_state
    dispense_tool = mcp._tool_manager._tools["dispense"]

    # Test minimum (10ml)
    tool_result = await dispense_tool.run(arguments={"ml": 10})
    result = json.loads(tool_result.content[0].text)
    assert result["dispensed"] == 10

    # Test maximum (100ml)
    tool_result = await dispense_tool.run(arguments={"ml": 100})
    result = json.loads(tool_result.content[0].text)
    assert result["dispensed"] == 100


@pytest.mark.asyncio
async def test_dispense_validation(setup_pump_state):
    """Test that invalid amounts are rejected"""
    mcp = setup_pump_state
    dispense_tool = mcp._tool_manager._tools["dispense"]

    # Test below minimum - FastMCP handles Pydantic validation
    with pytest.raises(Exception):  # Will be a Pydantic validation error
        await dispense_tool.run(arguments={"ml": 5})

    # Test above maximum
    with pytest.raises(Exception):  # Will be a Pydantic validation error
        await dispense_tool.run(arguments={"ml": 150})


@pytest.mark.asyncio
async def test_dispense_validation_non_integer_values(setup_pump_state):
    """Test that non-integer and invalid ml values are rejected"""
    mcp = setup_pump_state
    dispense_tool = mcp._tool_manager._tools["dispense"]

    # Test string value
    with pytest.raises(Exception):  # Pydantic validation error
        await dispense_tool.run(arguments={"ml": "fifty"})

    # Test float value
    with pytest.raises(Exception):  # Pydantic validation error
        await dispense_tool.run(arguments={"ml": 25.5})

    # Test None value
    with pytest.raises(Exception):  # Pydantic validation error
        await dispense_tool.run(arguments={"ml": None})

    # Test negative value
    with pytest.raises(Exception):  # Pydantic validation error
        await dispense_tool.run(arguments={"ml": -20})


@pytest.mark.asyncio
async def test_24h_limit_enforcement(setup_pump_state):
    """Test that 500ml/24h limit is enforced"""
    mcp = setup_pump_state
    dispense_tool = mcp._tool_manager._tools["dispense"]

    # Dispense 500ml total
    for _ in range(5):
        tool_result = await dispense_tool.run(arguments={"ml": 100})
        result = json.loads(tool_result.content[0].text)

    assert result["remaining_24h"] == 0

    # Next dispense should fail
    with pytest.raises(ValueError, match="Daily water limit"):
        await dispense_tool.run(arguments={"ml": 10})


@pytest.mark.asyncio
async def test_24h_rolling_window(setup_pump_state):
    """Test that the 24h limit is a rolling window"""
    mcp = setup_pump_state
    dispense_tool = mcp._tool_manager._tools["dispense"]

    with freeze_time("2024-01-01 12:00:00") as frozen_time:
        # Dispense 300ml
        await dispense_tool.run(arguments={"ml": 100})
        await dispense_tool.run(arguments={"ml": 100})
        await dispense_tool.run(arguments={"ml": 100})

        # Move forward 12 hours
        frozen_time.move_to("2024-01-02 00:00:00")

        # Should still count the 300ml (within 24h)
        tool_result = await dispense_tool.run(arguments={"ml": 100})
        result = json.loads(tool_result.content[0].text)
        assert result["remaining_24h"] == 100

        # Move forward another 13 hours (25 hours total from first dispense)
        frozen_time.move_to("2024-01-02 13:00:00")

        # First 300ml should no longer count
        tool_result = await dispense_tool.run(arguments={"ml": 100})
        result = json.loads(tool_result.content[0].text)
        assert result["remaining_24h"] == 300  # 500 - 200 (last two dispenses)


@pytest.mark.asyncio
async def test_get_usage_24h(setup_pump_state):
    """Test getting water usage statistics"""
    mcp = setup_pump_state
    dispense_tool = mcp._tool_manager._tools["dispense"]
    usage_tool = mcp._tool_manager._tools["get_usage_24h"]

    # Initially should be empty
    tool_result = await usage_tool.run(arguments={})
    result = json.loads(tool_result.content[0].text)
    assert result["used_ml"] == 0
    assert result["remaining_ml"] == 500
    assert result["events"] == 0

    # Dispense some water
    await dispense_tool.run(arguments={"ml": 50})
    await dispense_tool.run(arguments={"ml": 75})

    tool_result = await usage_tool.run(arguments={})
    result = json.loads(tool_result.content[0].text)
    assert result["used_ml"] == 125
    assert result["remaining_ml"] == 375
    assert result["events"] == 2


@pytest.mark.asyncio
async def test_partial_dispensing_at_limit(setup_pump_state):
    """Test that we dispense only what's available when near limit"""
    mcp = setup_pump_state
    dispense_tool = mcp._tool_manager._tools["dispense"]

    # Dispense 460ml
    for _ in range(4):
        await dispense_tool.run(arguments={"ml": 100})
    await dispense_tool.run(arguments={"ml": 60})

    # Try to dispense 100ml, should only get 40ml
    tool_result = await dispense_tool.run(arguments={"ml": 100})
    result = json.loads(tool_result.content[0].text)
    assert result["dispensed"] == 40
    assert result["remaining_24h"] == 0


@pytest.mark.asyncio
async def test_gatekeeper_enforcement(setup_pump_state):
    """Test that plant status must be written first"""
    mcp = setup_pump_state
    dispense_tool = mcp._tool_manager._tools["dispense"]

    # Reset the cycle status
    current_cycle_status["written"] = False

    with pytest.raises(ValueError, match="Must call write_status first"):
        await dispense_tool.run(arguments={"ml": 50})


# ===== State Persistence Tests =====


@pytest.mark.asyncio
async def test_state_file_creation(setup_pump_state):
    """Test that state file is created on first append (JSONL format)"""
    mcp = setup_pump_state
    dispense_tool = mcp._tool_manager._tools["dispense"]

    # State file should not exist initially
    assert not wp_module.water_history.file_path.exists()

    # Dispense water
    await dispense_tool.run(arguments={"ml": 50})

    # State file should now exist
    assert wp_module.water_history.file_path.exists()

    # Verify contents (JSONL format - each line is a JSON object)
    with open(wp_module.water_history.file_path, "r") as f:
        lines = f.readlines()
        assert len(lines) == 1
        event = json.loads(lines[0])
        assert event["ml"] == 50
        assert "timestamp" in event


@pytest.mark.asyncio
async def test_state_persistence_across_restarts(setup_pump_state):
    """Test that water history persists across server restarts"""
    mcp = setup_pump_state
    dispense_tool = mcp._tool_manager._tools["dispense"]

    # Dispense some water
    await dispense_tool.run(arguments={"ml": 50})
    await dispense_tool.run(arguments={"ml": 75})

    assert len(wp_module.water_history) == 2

    # Simulate restart by clearing in-memory state
    wp_module.water_history.clear()
    wp_module.water_history._loaded = False
    assert len(wp_module.water_history) == 0

    # Call a tool which should load state
    usage_tool = mcp._tool_manager._tools["get_usage_24h"]
    tool_result = await usage_tool.run(arguments={})
    result = json.loads(tool_result.content[0].text)

    # History should be restored
    assert len(wp_module.water_history) == 2
    assert result["used_ml"] == 125
    assert result["events"] == 2


@pytest.mark.asyncio
async def test_state_loading_on_first_tool_call(setup_pump_state):
    """Test that state is lazily loaded on first tool invocation (JSONL format)"""
    mcp = setup_pump_state

    # Manually create a JSONL state file with recent timestamps
    file_path = wp_module.water_history.file_path
    file_path.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now()
    test_history = [
        {"timestamp": (now - timedelta(hours=2)).isoformat(), "ml": 30},
        {"timestamp": (now - timedelta(hours=1)).isoformat(), "ml": 45},
    ]
    # Write as JSONL (one JSON object per line)
    with open(file_path, "w") as f:
        for event in test_history:
            f.write(json.dumps(event) + '\n')

    # Create new instance to simulate fresh load
    from utils.jsonl_history import JsonlHistory
    wp_module.water_history = JsonlHistory(file_path=file_path, max_memory_entries=1000)

    # Verify state is not loaded yet
    assert not wp_module.water_history._loaded
    assert len(wp_module.water_history) == 0

    # Call a tool
    usage_tool = mcp._tool_manager._tools["get_usage_24h"]
    tool_result = await usage_tool.run(arguments={})
    result = json.loads(tool_result.content[0].text)

    # State should now be loaded
    assert wp_module.water_history._loaded
    assert len(wp_module.water_history) == 2
    assert result["events"] == 2


@pytest.mark.asyncio
async def test_state_loads_only_once(setup_pump_state):
    """Test that state is loaded only once, not on every tool call (JSONL format)"""
    mcp = setup_pump_state
    dispense_tool = mcp._tool_manager._tools["dispense"]
    usage_tool = mcp._tool_manager._tools["get_usage_24h"]

    # Manually create a JSONL state file with recent timestamp
    file_path = wp_module.water_history.file_path
    file_path.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now()
    test_history = [{"timestamp": (now - timedelta(hours=1)).isoformat(), "ml": 30}]
    # Write as JSONL (one JSON object per line)
    with open(file_path, "w") as f:
        for event in test_history:
            f.write(json.dumps(event) + '\n')

    # Create new instance to simulate fresh load
    from utils.jsonl_history import JsonlHistory
    wp_module.water_history = JsonlHistory(file_path=file_path, max_memory_entries=1000)

    # First tool call should load state
    await usage_tool.run(arguments={})
    assert wp_module.water_history._loaded
    assert len(wp_module.water_history) == 1

    # Manually modify the file (simulating external change)
    with open(file_path, "w") as f:
        json.dump({"water_history": []}, f)

    # Second tool call should NOT reload state
    await dispense_tool.run(arguments={"ml": 50})

    # Should still have the original loaded state plus the new dispense
    assert len(wp_module.water_history) == 2

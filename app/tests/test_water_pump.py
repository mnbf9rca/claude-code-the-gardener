"""
Unit Tests for Water Pump Module with ESP32 HTTP Integration

These tests verify the water pump functionality including:
- Dispensing water via ESP32 HTTP API
- ML-to-seconds conversion
- 24-hour rolling limit enforcement
- Usage tracking and reporting
- State persistence and recovery
"""
import os

# Set test environment variables BEFORE any imports
os.environ["ESP32_HOST"] = "192.168.1.100"
os.environ["ESP32_PORT"] = "80"
os.environ["PUMP_ML_PER_SECOND"] = "0.9"

from dotenv import load_dotenv

# Load environment variables from .env file (test values take precedence)
load_dotenv(override=False)

import pytest
import pytest_asyncio
import json
import httpx
from datetime import datetime, timedelta, timezone
from freezegun import freeze_time
from fastmcp import FastMCP
from utils.shared_state import reset_cycle, current_cycle_status
import tools.water_pump as wp_module
from tools.water_pump import setup_water_pump_tools


@pytest.fixture
def esp32_base_url():
    """Get ESP32 base URL for mocking"""
    from utils.esp32_config import get_esp32_config
    return get_esp32_config().base_url


@pytest_asyncio.fixture(autouse=True)
async def setup_pump_state(tmp_path):
    """Reset water pump state before each test"""
    # Reset cycle state
    reset_cycle()
    current_cycle_status["written"] = True  # Allow tool calls

    # Reset ESP32 config singleton
    import utils.esp32_config
    utils.esp32_config._config = None

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
async def test_dispense_basic(setup_pump_state, httpx_mock, esp32_base_url):
    """Test basic water dispensing via ESP32"""
    mcp = setup_pump_state

    # Mock ESP32 successful response
    httpx_mock.add_response(
        url=f"{esp32_base_url}/pump",
        method="POST",
        json={"success": True, "duration": 22, "timestamp": "2025-01-23T14:30:00Z"}
    )

    dispense_tool = mcp._tool_manager._tools["dispense_water"]
    tool_result = await dispense_tool.run(arguments={"ml": 20})
    result = json.loads(tool_result.content[0].text)

    assert result["dispensed"] == 20
    assert result["remaining_24h"] == 480  # 500 - 20
    assert "timestamp" in result
    assert len(wp_module.water_history) == 1

    # Verify ML-to-seconds conversion (20ml / 0.9 ml/s = ~22s)
    # Access via public API
    history = list(wp_module.water_history.get_all())
    assert history[0]["seconds"] == 22


@pytest.mark.asyncio
async def test_dispense_minimum_maximum(setup_pump_state, httpx_mock, esp32_base_url):
    """Test min/max dispensing limits"""
    mcp = setup_pump_state

    # Mock responses for both dispenses
    httpx_mock.add_response(
        url=f"{esp32_base_url}/pump",
        method="POST",
        json={"success": True, "duration": 11, "timestamp": "2025-01-23T14:30:00Z"}
    )
    httpx_mock.add_response(
        url=f"{esp32_base_url}/pump",
        method="POST",
        json={"success": True, "duration": 28, "timestamp": "2025-01-23T14:30:05Z"}
    )

    dispense_tool = mcp._tool_manager._tools["dispense_water"]

    # Test minimum (10ml)
    tool_result = await dispense_tool.run(arguments={"ml": 10})
    result = json.loads(tool_result.content[0].text)
    assert result["dispensed"] == 10

    # Test maximum (25ml)
    tool_result = await dispense_tool.run(arguments={"ml": 25})
    result = json.loads(tool_result.content[0].text)
    assert result["dispensed"] == 25


@pytest.mark.asyncio
async def test_dispense_validation(setup_pump_state):
    """Test that invalid amounts are rejected"""
    mcp = setup_pump_state
    dispense_tool = mcp._tool_manager._tools["dispense_water"]

    # Test below minimum - FastMCP handles Pydantic validation
    with pytest.raises(Exception):  # Will be a Pydantic validation error
        await dispense_tool.run(arguments={"ml": 5})

    # Test above maximum
    with pytest.raises(Exception):  # Will be a Pydantic validation error
        await dispense_tool.run(arguments={"ml": 26})


@pytest.mark.asyncio
async def test_dispense_validation_non_integer_values(setup_pump_state):
    """Test that non-integer and invalid ml values are rejected"""
    mcp = setup_pump_state
    dispense_tool = mcp._tool_manager._tools["dispense_water"]

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
async def test_24h_limit_enforcement(setup_pump_state, httpx_mock, esp32_base_url):
    """Test that 500ml/24h limit is enforced"""
    mcp = setup_pump_state

    # Mock 20 successful dispenses
    for _ in range(20):
        httpx_mock.add_response(
            url=f"{esp32_base_url}/pump",
            method="POST",
            json={"success": True, "duration": 28, "timestamp": "2025-01-23T14:30:00Z"}
        )

    dispense_tool = mcp._tool_manager._tools["dispense_water"]

    # Dispense 500ml total (20 × 25ml)
    for _ in range(20):
        tool_result = await dispense_tool.run(arguments={"ml": 25})
        result = json.loads(tool_result.content[0].text)

    assert result["remaining_24h"] == 0

    # Next dispense should fail
    with pytest.raises(ValueError, match="Daily water limit"):
        await dispense_tool.run(arguments={"ml": 10})


@pytest.mark.asyncio
async def test_24h_rolling_window(setup_pump_state, httpx_mock, esp32_base_url):
    """Test that the 24h limit is a rolling window"""
    mcp = setup_pump_state

    # Mock successful responses
    for _ in range(5):
        httpx_mock.add_response(
            url=f"{esp32_base_url}/pump",
            method="POST",
            json={"success": True, "duration": 28, "timestamp": "2025-01-23T14:30:00Z"}
        )

    dispense_tool = mcp._tool_manager._tools["dispense_water"]

    with freeze_time("2024-01-01 12:00:00") as frozen_time:
        # Dispense 75ml (3 × 25ml)
        await dispense_tool.run(arguments={"ml": 25})
        await dispense_tool.run(arguments={"ml": 25})
        await dispense_tool.run(arguments={"ml": 25})

        # Move forward 12 hours
        frozen_time.move_to("2024-01-02 00:00:00")

        # Should still count the 75ml (within 24h)
        tool_result = await dispense_tool.run(arguments={"ml": 25})
        result = json.loads(tool_result.content[0].text)
        assert result["remaining_24h"] == 400  # 500 - 100

        # Move forward another 13 hours (25 hours total from first dispense)
        frozen_time.move_to("2024-01-02 13:00:00")

        # First 75ml should no longer count
        tool_result = await dispense_tool.run(arguments={"ml": 25})
        result = json.loads(tool_result.content[0].text)
        assert result["remaining_24h"] == 450  # 500 - 50 (last two dispenses)


@pytest.mark.asyncio
async def test_get_usage_24h(setup_pump_state, httpx_mock, esp32_base_url):
    """Test getting water usage statistics"""
    mcp = setup_pump_state

    # Mock responses for dispenses
    httpx_mock.add_response(
        url=f"{esp32_base_url}/pump",
        method="POST",
        json={"success": True, "duration": 22, "timestamp": "2025-01-23T14:30:00Z"}
    )
    httpx_mock.add_response(
        url=f"{esp32_base_url}/pump",
        method="POST",
        json={"success": True, "duration": 21, "timestamp": "2025-01-23T14:30:05Z"}
    )

    dispense_tool = mcp._tool_manager._tools["dispense_water"]
    usage_tool = mcp._tool_manager._tools["get_water_usage_24h"]

    # Initially should be empty
    tool_result = await usage_tool.run(arguments={})
    result = json.loads(tool_result.content[0].text)
    assert result["used_ml"] == 0
    assert result["remaining_ml"] == 500
    assert result["events"] == 0

    # Dispense some water
    await dispense_tool.run(arguments={"ml": 20})
    await dispense_tool.run(arguments={"ml": 25})

    tool_result = await usage_tool.run(arguments={})
    result = json.loads(tool_result.content[0].text)
    assert result["used_ml"] == 45  # 20 + 25
    assert result["remaining_ml"] == 455  # 500 - 45
    assert result["events"] == 2


@pytest.mark.asyncio
async def test_partial_dispensing_at_limit(setup_pump_state, httpx_mock, esp32_base_url):
    """Test that we dispense only what's available when near limit"""
    mcp = setup_pump_state

    # Mock responses for dispenses (need 20 dispenses + 1 partial)
    for _ in range(21):
        httpx_mock.add_response(
            url=f"{esp32_base_url}/pump",
            method="POST",
            json={"success": True, "duration": 20, "timestamp": "2025-01-23T14:30:00Z"}
        )

    dispense_tool = mcp._tool_manager._tools["dispense_water"]

    # Dispense 490ml (19×25ml + 1×15ml)
    for _ in range(19):
        await dispense_tool.run(arguments={"ml": 25})
    await dispense_tool.run(arguments={"ml": 15})

    # Try to dispense 25ml, should only get 10ml (partial)
    tool_result = await dispense_tool.run(arguments={"ml": 25})
    result = json.loads(tool_result.content[0].text)
    assert result["dispensed"] == 10  # Only 10ml remaining
    assert result["remaining_24h"] == 0


@pytest.mark.asyncio
async def test_gatekeeper_enforcement(setup_pump_state):
    """Test that plant status must be written first"""
    mcp = setup_pump_state
    dispense_tool = mcp._tool_manager._tools["dispense_water"]

    # Reset the cycle status
    current_cycle_status["written"] = False

    with pytest.raises(ValueError, match="Must call write_status first"):
        await dispense_tool.run(arguments={"ml": 20})


@pytest.mark.asyncio
async def test_esp32_timeout(setup_pump_state, httpx_mock, esp32_base_url):
    """Test handling of ESP32 timeout"""
    mcp = setup_pump_state

    # Mock timeout using httpx.TimeoutException
    httpx_mock.add_exception(
        httpx.TimeoutException("Connection timeout"),
        url=f"{esp32_base_url}/pump"
    )

    dispense_tool = mcp._tool_manager._tools["dispense_water"]

    # Should handle timeout gracefully
    with pytest.raises(ValueError, match="timeout"):
        await dispense_tool.run(arguments={"ml": 20})


@pytest.mark.asyncio
async def test_esp32_pump_already_active(setup_pump_state, httpx_mock, esp32_base_url):
    """Test handling when ESP32 reports pump already active"""
    mcp = setup_pump_state

    # Mock 409 Conflict response
    httpx_mock.add_response(
        url=f"{esp32_base_url}/pump",
        method="POST",
        status_code=409,
        json={"success": False, "error": "Pump already active"}
    )

    dispense_tool = mcp._tool_manager._tools["dispense_water"]

    # Should handle 409 error gracefully
    with pytest.raises(ValueError, match="409"):
        await dispense_tool.run(arguments={"ml": 20})


@pytest.mark.asyncio
async def test_esp32_malformed_json(setup_pump_state, httpx_mock, esp32_base_url):
    """Test handling of malformed JSON response from ESP32"""
    mcp = setup_pump_state

    # Mock malformed JSON response
    httpx_mock.add_response(
        url=f"{esp32_base_url}/pump",
        method="POST",
        text="not valid json",
        status_code=200
    )

    dispense_tool = mcp._tool_manager._tools["dispense_water"]

    # Should handle malformed JSON gracefully
    with pytest.raises(ValueError, match="Invalid JSON format"):
        await dispense_tool.run(arguments={"ml": 20})


@pytest.mark.asyncio
async def test_ml_to_seconds_conversion(setup_pump_state, httpx_mock, esp32_base_url):
    """Test ML-to-seconds conversion logic"""
    mcp = setup_pump_state

    # Mock response
    httpx_mock.add_response(
        url=f"{esp32_base_url}/pump",
        method="POST",
        json={"success": True, "duration": 22, "timestamp": "2025-01-23T14:30:00Z"}
    )

    dispense_tool = mcp._tool_manager._tools["dispense_water"]

    # 20ml / 0.9 ml/s = 22.22s, rounds to 22s
    await dispense_tool.run(arguments={"ml": 20})

    # Check the request was made with correct seconds
    requests = httpx_mock.get_requests()
    assert len(requests) == 1
    request_body = json.loads(requests[0].content)
    assert request_body["seconds"] == 22


# ===== State Persistence Tests =====


@pytest.mark.asyncio
async def test_state_file_creation(setup_pump_state, httpx_mock, esp32_base_url):
    """Test that state file is created on first append (JSONL format)"""
    mcp = setup_pump_state

    # Mock ESP32 response
    httpx_mock.add_response(
        url=f"{esp32_base_url}/pump",
        method="POST",
        json={"success": True, "duration": 22, "timestamp": "2025-01-23T14:30:00Z"}
    )

    dispense_tool = mcp._tool_manager._tools["dispense_water"]

    # State file should not exist initially
    assert not wp_module.water_history.file_path.exists()

    # Dispense water
    await dispense_tool.run(arguments={"ml": 20})

    # State file should now exist
    assert wp_module.water_history.file_path.exists()

    # Verify contents (JSONL format - each line is a JSON object)
    with open(wp_module.water_history.file_path, "r") as f:
        lines = f.readlines()
        assert len(lines) == 1
        event = json.loads(lines[0])
        assert event["ml"] == 20
        assert event["seconds"] == 22
        assert "timestamp" in event


@pytest.mark.asyncio
async def test_state_persistence_across_restarts(setup_pump_state, httpx_mock, esp32_base_url):
    """Test that water history persists across server restarts"""
    mcp = setup_pump_state

    # Mock responses
    httpx_mock.add_response(
        url=f"{esp32_base_url}/pump",
        method="POST",
        json={"success": True, "duration": 22, "timestamp": "2025-01-23T14:30:00Z"}
    )
    httpx_mock.add_response(
        url=f"{esp32_base_url}/pump",
        method="POST",
        json={"success": True, "duration": 21, "timestamp": "2025-01-23T14:30:05Z"}
    )

    dispense_tool = mcp._tool_manager._tools["dispense_water"]

    # Dispense some water
    await dispense_tool.run(arguments={"ml": 20})
    await dispense_tool.run(arguments={"ml": 25})

    assert len(wp_module.water_history) == 2

    # Simulate restart by clearing in-memory state
    wp_module.water_history.clear()
    wp_module.water_history._loaded = False
    assert len(wp_module.water_history) == 0

    # Call a tool which should load state
    usage_tool = mcp._tool_manager._tools["get_water_usage_24h"]
    tool_result = await usage_tool.run(arguments={})
    result = json.loads(tool_result.content[0].text)

    # History should be restored
    assert len(wp_module.water_history) == 2
    assert result["used_ml"] == 45  # 20 + 25
    assert result["events"] == 2


@pytest.mark.asyncio
async def test_state_loading_on_first_tool_call(setup_pump_state):
    """Test that state is lazily loaded on first tool invocation (JSONL format)"""
    mcp = setup_pump_state

    # Manually create a JSONL state file with recent timestamps
    file_path = wp_module.water_history.file_path
    file_path.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    test_history = [
        {"timestamp": (now - timedelta(hours=2)).isoformat(), "ml": 20, "seconds": 9},
        {"timestamp": (now - timedelta(hours=1)).isoformat(), "ml": 25, "seconds": 13},
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
    usage_tool = mcp._tool_manager._tools["get_water_usage_24h"]
    tool_result = await usage_tool.run(arguments={})
    result = json.loads(tool_result.content[0].text)

    # State should now be loaded
    assert wp_module.water_history._loaded
    assert len(wp_module.water_history) == 2
    assert result["events"] == 2


@pytest.mark.asyncio
async def test_state_loads_only_once(setup_pump_state, httpx_mock, esp32_base_url):
    """Test that state is loaded only once, not on every tool call (JSONL format)"""
    mcp = setup_pump_state

    # Mock ESP32 response
    httpx_mock.add_response(
        url=f"{esp32_base_url}/pump",
        method="POST",
        json={"success": True, "duration": 22, "timestamp": "2025-01-23T14:30:00Z"}
    )

    dispense_tool = mcp._tool_manager._tools["dispense_water"]
    usage_tool = mcp._tool_manager._tools["get_water_usage_24h"]

    # Manually create a JSONL state file with recent timestamp
    file_path = wp_module.water_history.file_path
    file_path.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    test_history = [{"timestamp": (now - timedelta(hours=1)).isoformat(), "ml": 20, "seconds": 9}]
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
    await dispense_tool.run(arguments={"ml": 20})

    # Should still have the original loaded state plus the new dispense
    assert len(wp_module.water_history) == 2


@pytest.mark.asyncio
@freeze_time("2025-01-24 12:00:00")
async def test_get_water_history_sampling(setup_pump_state):
    """Test get_water_history with sampling mode"""
    mcp = setup_pump_state

    # Add some test data
    base_time = datetime(2025, 1, 24, 11, 0, 0, tzinfo=timezone.utc)
    for i in range(5):
        wp_module.water_history.append({
            "timestamp": (base_time + timedelta(minutes=i*10)).isoformat(),
            "ml": 25 + i*10
        })

    # Test sampling mode (middle)
    history_tool = mcp._tool_manager._tools["get_water_history"]
    result = await history_tool.run(arguments={
        "hours": 1,
        "samples_per_hour": 6,
        "aggregation": "middle"
    })

    history = json.loads(result.content[0].text)

    # Should return sampled entries with original structure
    assert isinstance(history, list)
    assert len(history) > 0
    for entry in history:
        assert "timestamp" in entry
        assert "ml" in entry


@pytest.mark.asyncio
@freeze_time("2025-01-24 12:00:00")
async def test_get_water_history_aggregation_count(setup_pump_state):
    """Test get_water_history with count aggregation"""
    mcp = setup_pump_state

    # Add test data
    base_time = datetime(2025, 1, 24, 11, 0, 0, tzinfo=timezone.utc)
    for i in range(3):
        wp_module.water_history.append({
            "timestamp": (base_time + timedelta(minutes=i)).isoformat(),
            "ml": 50
        })

    # Test count aggregation
    history_tool = mcp._tool_manager._tools["get_water_history"]
    result = await history_tool.run(arguments={
        "hours": 1,
        "samples_per_hour": 6,
        "aggregation": "count"
    })

    history = json.loads(result.content[0].text)

    # Should return bucket statistics
    assert isinstance(history, list)
    assert len(history) > 0
    for bucket in history:
        assert "bucket_start" in bucket
        assert "bucket_end" in bucket
        assert "value" in bucket
        assert "count" in bucket


@pytest.mark.asyncio
@freeze_time("2025-01-24 12:00:00")
async def test_get_water_history_aggregation_sum(setup_pump_state):
    """Test get_water_history with sum aggregation"""
    mcp = setup_pump_state

    # Add test data
    base_time = datetime(2025, 1, 24, 11, 0, 0, tzinfo=timezone.utc)
    for i in range(3):
        wp_module.water_history.append({
            "timestamp": (base_time + timedelta(minutes=i)).isoformat(),
            "ml": 25
        })

    # Test sum aggregation
    history_tool = mcp._tool_manager._tools["get_water_history"]
    result = await history_tool.run(arguments={
        "hours": 1,
        "samples_per_hour": 6,
        "aggregation": "sum",
        "value_field": "ml"
    })

    history = json.loads(result.content[0].text)

    # Should return bucket statistics with summed values
    assert isinstance(history, list)
    assert len(history) == 1  # All entries in one bucket
    assert history[0]["value"] == 75  # 3 * 25ml
    assert history[0]["count"] == 3


@pytest.mark.asyncio
@freeze_time("2025-01-24 12:00:00")
async def test_get_water_history_aggregation_mean(setup_pump_state):
    """Test get_water_history with mean aggregation"""
    mcp = setup_pump_state

    # Add test data with varying amounts
    base_time = datetime(2025, 1, 24, 11, 0, 0, tzinfo=timezone.utc)
    wp_module.water_history.append({
        "timestamp": (base_time + timedelta(minutes=0)).isoformat(),
        "ml": 50
    })
    wp_module.water_history.append({
        "timestamp": (base_time + timedelta(minutes=1)).isoformat(),
        "ml": 25
    })
    wp_module.water_history.append({
        "timestamp": (base_time + timedelta(minutes=2)).isoformat(),
        "ml": 30
    })

    # Test mean aggregation
    history_tool = mcp._tool_manager._tools["get_water_history"]
    result = await history_tool.run(arguments={
        "hours": 1,
        "samples_per_hour": 6,
        "aggregation": "mean",
        "value_field": "ml"
    })

    history = json.loads(result.content[0].text)

    # Should return bucket statistics with averaged values
    assert isinstance(history, list)
    assert len(history) == 1  # All entries in one bucket
    assert history[0]["value"] == 35.0  # (50 + 25 + 30) / 3 = 105 / 3 = 35
    assert history[0]["count"] == 3

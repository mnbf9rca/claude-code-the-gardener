"""
Unit Tests for Thinking Module

These tests verify the thinking functionality including:
- Logging structured thoughts
- Retrieving recent thoughts
- Time range queries
- Keyword searching
- State persistence and recovery
- Pagination
"""

import pytest
import pytest_asyncio
import json
from datetime import datetime, timedelta, timezone
from freezegun import freeze_time
from fastmcp import FastMCP
import tools.thinking as thinking_module
from tools.thinking import setup_thinking_tools
from pathlib import Path


@pytest_asyncio.fixture(autouse=True)
async def setup_thinking_state(tmp_path):
    """Reset thinking state before each test"""
    # Use temp directory for state file (don't touch production state!)
    from utils.jsonl_history import JsonlHistory

    original_history = thinking_module.thought_history

    # Create new history instance with temp file
    thinking_module.thought_history = JsonlHistory(
        file_path=tmp_path / "thinking.jsonl",
        max_memory_entries=1000
    )

    # Create MCP instance and setup tools
    mcp = FastMCP("test")
    setup_thinking_tools(mcp)

    yield mcp

    # Restore original history
    thinking_module.thought_history = original_history


@pytest.mark.asyncio
async def test_log_thought_basic(setup_thinking_state):
    """Test basic thought logging"""
    mcp = setup_thinking_state
    log_thought_tool = mcp._tool_manager._tools["log_thought"]

    tool_result = await log_thought_tool.run(arguments={
        "observation": "Moisture sensor reading dropped to 1200",
        "hypothesis": "Soil is drying out faster than expected",
        "candidate_actions": [
            {"order": 1, "action": "water", "value": 40},
            {"order": 2, "action": "observe", "value": None}
        ],
        "reasoning": "Gradual watering is safer than a large amount",
        "uncertainties": "Not sure if the sensor calibration is accurate",
        "tags": ["moisture", "watering"]
    })
    result = json.loads(tool_result.content[0].text)

    assert result["success"] is True
    assert "timestamp" in result
    assert len(thinking_module.thought_history) == 1

    # Verify stored thought
    thoughts = thinking_module.thought_history.get_all()
    assert len(thoughts) == 1
    thought = thoughts[0]
    assert thought["observation"] == "Moisture sensor reading dropped to 1200"
    assert thought["hypothesis"] == "Soil is drying out faster than expected"
    assert len(thought["candidate_actions"]) == 2
    assert thought["tags"] == ["moisture", "watering"]


@pytest.mark.asyncio
async def test_log_thought_minimal(setup_thinking_state):
    """Test logging thought with minimal fields"""
    mcp = setup_thinking_state
    log_thought_tool = mcp._tool_manager._tools["log_thought"]

    tool_result = await log_thought_tool.run(arguments={
        "observation": "Plant looks healthy",
        "hypothesis": "Current care routine is working",
        "candidate_actions": [],
        "reasoning": "No changes needed",
        "uncertainties": "None",
        "tags": []
    })
    result = json.loads(tool_result.content[0].text)

    assert result["success"] is True
    assert len(thinking_module.thought_history) == 1


@pytest.mark.asyncio
async def test_log_thought_malformed_candidate_actions(setup_thinking_state):
    """Test that malformed candidate_actions types are rejected"""
    mcp = setup_thinking_state
    log_thought_tool = mcp._tool_manager._tools["log_thought"]

    # Pass a string instead of a list for candidate_actions
    with pytest.raises(Exception):  # Will be a Pydantic validation error
        await log_thought_tool.run(arguments={
            "observation": "Test observation",
            "hypothesis": "Test hypothesis",
            "candidate_actions": "this should be a list",
            "reasoning": "Testing",
            "uncertainties": "None",
            "tags": []
        })

    # Note: The tool accepts List[Dict[str, Any]], so it doesn't validate
    # the structure of individual dict items. This is intentional to allow
    # flexibility in what candidate_actions can contain.


@pytest.mark.asyncio
async def test_get_recent_default(setup_thinking_state):
    """Test getting recent thoughts with default limit"""
    mcp = setup_thinking_state
    log_thought_tool = mcp._tool_manager._tools["log_thought"]
    get_recent_tool = mcp._tool_manager._tools["get_recent_thoughts"]

    # Log 5 thoughts
    for i in range(5):
        await log_thought_tool.run(arguments={
            "observation": f"Observation {i}",
            "hypothesis": f"Hypothesis {i}",
            "candidate_actions": [],
            "reasoning": "Testing",
            "uncertainties": "None",
            "tags": []
        })

    # Get recent (default 3)
    tool_result = await get_recent_tool.run(arguments={})
    result = json.loads(tool_result.content[0].text)

    assert result["count"] == 3
    assert len(result["thoughts"]) == 3
    # Should get the 3 most recent (2, 3, 4)
    assert result["thoughts"][0]["observation"] == "Observation 2"
    assert result["thoughts"][2]["observation"] == "Observation 4"


@pytest.mark.asyncio
async def test_get_recent_custom_limit(setup_thinking_state):
    """Test getting recent thoughts with custom limit"""
    mcp = setup_thinking_state
    log_thought_tool = mcp._tool_manager._tools["log_thought"]
    get_recent_tool = mcp._tool_manager._tools["get_recent_thoughts"]

    # Log 10 thoughts
    for i in range(10):
        await log_thought_tool.run(arguments={
            "observation": f"Observation {i}",
            "hypothesis": f"Hypothesis {i}",
            "candidate_actions": [],
            "reasoning": "Testing",
            "uncertainties": "None",
            "tags": []
        })

    # Get recent 7
    tool_result = await get_recent_tool.run(arguments={"n": 7})
    result = json.loads(tool_result.content[0].text)

    assert result["count"] == 7
    assert result["thoughts"][0]["observation"] == "Observation 3"
    assert result["thoughts"][6]["observation"] == "Observation 9"


@pytest.mark.asyncio
async def test_get_recent_pagination(setup_thinking_state):
    """Test pagination with offset"""
    mcp = setup_thinking_state
    log_thought_tool = mcp._tool_manager._tools["log_thought"]
    get_recent_tool = mcp._tool_manager._tools["get_recent_thoughts"]

    # Log 10 thoughts
    for i in range(10):
        await log_thought_tool.run(arguments={
            "observation": f"Observation {i}",
            "hypothesis": f"Hypothesis {i}",
            "candidate_actions": [],
            "reasoning": "Testing",
            "uncertainties": "None",
            "tags": []
        })

    # Get 3 recent with offset 5 (skip 5 most recent, get 3 before that)
    tool_result = await get_recent_tool.run(arguments={"n": 3, "offset": 5})
    result = json.loads(tool_result.content[0].text)

    assert result["count"] == 3
    # Should get entries 2, 3, 4 (offset 5 from end skips 5-9, then take 3)
    assert result["thoughts"][0]["observation"] == "Observation 2"
    assert result["thoughts"][2]["observation"] == "Observation 4"


@pytest.mark.asyncio
async def test_get_range(setup_thinking_state):
    """Test getting thoughts within a time range"""
    mcp = setup_thinking_state
    log_thought_tool = mcp._tool_manager._tools["log_thought"]
    get_range_tool = mcp._tool_manager._tools["get_thoughts_in_range"]

    base_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

    # Log thoughts at different times
    for i in range(5):
        with freeze_time(base_time + timedelta(hours=i)):
            await log_thought_tool.run(arguments={
                "observation": f"Observation at hour {i}",
                "hypothesis": f"Hypothesis {i}",
                "candidate_actions": [],
                "reasoning": "Testing",
                "uncertainties": "None",
                "tags": []
            })

    # Query for thoughts between hour 1 and hour 3
    start_time = (base_time + timedelta(hours=1)).isoformat()
    end_time = (base_time + timedelta(hours=3)).isoformat()

    tool_result = await get_range_tool.run(arguments={
        "start_time": start_time,
        "end_time": end_time
    })
    result = json.loads(tool_result.content[0].text)

    assert result["count"] == 3  # Hours 1, 2, 3
    assert "hour 1" in result["thoughts"][0]["observation"]
    assert "hour 3" in result["thoughts"][2]["observation"]


@pytest.mark.asyncio
async def test_search_keyword(setup_thinking_state):
    """Test searching for keywords in thoughts"""
    mcp = setup_thinking_state
    log_thought_tool = mcp._tool_manager._tools["log_thought"]
    search_tool = mcp._tool_manager._tools["search_thoughts"]

    # Log thoughts with different keywords
    await log_thought_tool.run(arguments={
        "observation": "Moisture sensor shows low reading",
        "hypothesis": "Soil needs water",
        "candidate_actions": [],
        "reasoning": "Sensor calibration looks good",
        "uncertainties": "None",
        "tags": ["moisture"]
    })

    await log_thought_tool.run(arguments={
        "observation": "Light duration was 2 hours",
        "hypothesis": "Plant getting enough light",
        "candidate_actions": [],
        "reasoning": "Growth looks healthy",
        "uncertainties": "None",
        "tags": ["light"]
    })

    await log_thought_tool.run(arguments={
        "observation": "Temperature is stable",
        "hypothesis": "Environment is optimal",
        "candidate_actions": [],
        "reasoning": "No moisture issues",
        "uncertainties": "None",
        "tags": ["environment"]
    })

    # Search for "moisture"
    tool_result = await search_tool.run(arguments={"keyword": "moisture"})
    result = json.loads(tool_result.content[0].text)

    assert result["count"] == 2  # Found in 1st and 3rd thoughts
    assert any("sensor" in t["observation"].lower() for t in result["thoughts"])


@pytest.mark.asyncio
async def test_search_case_insensitive(setup_thinking_state):
    """Test that search is case-insensitive"""
    mcp = setup_thinking_state
    log_thought_tool = mcp._tool_manager._tools["log_thought"]
    search_tool = mcp._tool_manager._tools["search_thoughts"]

    await log_thought_tool.run(arguments={
        "observation": "MOISTURE level is LOW",
        "hypothesis": "Needs watering",
        "candidate_actions": [],
        "reasoning": "Testing",
        "uncertainties": "None",
        "tags": []
    })

    # Search with lowercase
    tool_result = await search_tool.run(arguments={"keyword": "moisture"})
    result = json.loads(tool_result.content[0].text)

    assert result["count"] == 1


@pytest.mark.asyncio
async def test_search_time_window(setup_thinking_state):
    """Test search respects time window"""
    mcp = setup_thinking_state
    log_thought_tool = mcp._tool_manager._tools["log_thought"]
    search_tool = mcp._tool_manager._tools["search_thoughts"]

    base_time = datetime.now()

    # Log thought 30 hours ago
    with freeze_time(base_time - timedelta(hours=30)):
        await log_thought_tool.run(arguments={
            "observation": "Old moisture reading",
            "hypothesis": "Testing",
            "candidate_actions": [],
            "reasoning": "Testing",
            "uncertainties": "None",
            "tags": []
        })

    # Log thought 10 hours ago
    with freeze_time(base_time - timedelta(hours=10)):
        await log_thought_tool.run(arguments={
            "observation": "Recent moisture reading",
            "hypothesis": "Testing",
            "candidate_actions": [],
            "reasoning": "Testing",
            "uncertainties": "None",
            "tags": []
        })

    # Search for "moisture" in last 24 hours
    with freeze_time(base_time):
        tool_result = await search_tool.run(arguments={"keyword": "moisture", "hours": 24})
        result = json.loads(tool_result.content[0].text)

    assert result["count"] == 1  # Only the recent one
    assert "Recent" in result["thoughts"][0]["observation"]


@pytest.mark.asyncio
async def test_state_persistence(setup_thinking_state):
    """Test that thoughts are persisted to disk"""
    mcp = setup_thinking_state
    log_thought_tool = mcp._tool_manager._tools["log_thought"]

    # Log a thought
    await log_thought_tool.run(arguments={
        "observation": "Test observation",
        "hypothesis": "Test hypothesis",
        "candidate_actions": [{"order": 1, "action": "test", "value": 42}],
        "reasoning": "Test reasoning",
        "uncertainties": "Test uncertainties",
        "tags": ["test"]
    })

    # Verify file was created
    assert thinking_module.thought_history.file_path.exists()

    # Read the file
    with open(thinking_module.thought_history.file_path, 'r') as f:
        lines = f.readlines()

    assert len(lines) == 1
    stored = json.loads(lines[0])
    assert stored["observation"] == "Test observation"
    assert stored["hypothesis"] == "Test hypothesis"
    assert len(stored["candidate_actions"]) == 1


@pytest.mark.asyncio
async def test_state_recovery(setup_thinking_state):
    """Test that state is recovered from disk on restart"""
    mcp = setup_thinking_state
    log_thought_tool = mcp._tool_manager._tools["log_thought"]
    get_recent_tool = mcp._tool_manager._tools["get_recent_thoughts"]

    # Log some thoughts
    for i in range(3):
        await log_thought_tool.run(arguments={
            "observation": f"Observation {i}",
            "hypothesis": f"Hypothesis {i}",
            "candidate_actions": [],
            "reasoning": "Testing",
            "uncertainties": "None",
            "tags": []
        })

    # Clear memory (simulating restart) and create new instance
    file_path = thinking_module.thought_history.file_path
    from utils.jsonl_history import JsonlHistory
    thinking_module.thought_history = JsonlHistory(file_path=file_path, max_memory_entries=1000)

    # Query should trigger state load
    tool_result = await get_recent_tool.run(arguments={"n": 5})
    result = json.loads(tool_result.content[0].text)

    assert result["count"] == 3
    assert result["thoughts"][0]["observation"] == "Observation 0"


@pytest.mark.asyncio
async def test_memory_pruning(setup_thinking_state):
    """Test that memory is pruned to MAX_MEMORY_ENTRIES"""
    mcp = setup_thinking_state
    log_thought_tool = mcp._tool_manager._tools["log_thought"]

    # Temporarily set a low max for testing
    original_max = thinking_module.thought_history.max_memory_entries
    thinking_module.thought_history.max_memory_entries = 5

    # Log 10 thoughts
    for i in range(10):
        await log_thought_tool.run(arguments={
            "observation": f"Observation {i}",
            "hypothesis": f"Hypothesis {i}",
            "candidate_actions": [],
            "reasoning": "Testing",
            "uncertainties": "None",
            "tags": []
        })

    # Memory should be pruned to 5
    assert len(thinking_module.thought_history) == 5
    # Should keep the most recent 5 (5-9)
    all_thoughts = thinking_module.thought_history.get_all()
    assert all_thoughts[0]["observation"] == "Observation 5"

    # Restore original max
    thinking_module.thought_history.max_memory_entries = original_max


@pytest.mark.asyncio
async def test_get_recent_empty(setup_thinking_state):
    """Test getting recent thoughts when none exist"""
    mcp = setup_thinking_state
    get_recent_tool = mcp._tool_manager._tools["get_recent_thoughts"]

    tool_result = await get_recent_tool.run(arguments={})
    result = json.loads(tool_result.content[0].text)

    assert result["count"] == 0
    assert result["thoughts"] == []


@pytest.mark.asyncio
async def test_search_no_results(setup_thinking_state):
    """Test search when no results match"""
    mcp = setup_thinking_state
    log_thought_tool = mcp._tool_manager._tools["log_thought"]
    search_tool = mcp._tool_manager._tools["search_thoughts"]

    await log_thought_tool.run(arguments={
        "observation": "Test observation",
        "hypothesis": "Test hypothesis",
        "candidate_actions": [],
        "reasoning": "Testing",
        "uncertainties": "None",
        "tags": []
    })

    tool_result = await search_tool.run(arguments={"keyword": "nonexistent"})
    result = json.loads(tool_result.content[0].text)

    assert result["count"] == 0
    assert result["thoughts"] == []


@pytest.mark.asyncio
@freeze_time("2025-01-24 12:00:00")
async def test_get_thought_history_bucketed_sampling(setup_thinking_state):
    """Test get_thought_history_bucketed with sampling mode"""
    mcp = setup_thinking_state

    # Add test data
    base_time = datetime(2025, 1, 24, 11, 0, 0, tzinfo=timezone.utc)
    for i in range(5):
        thinking_module.thought_history.append({
            "timestamp": (base_time + timedelta(minutes=i*10)).isoformat(),
            "observation": f"Observation {i}",
            "hypothesis": f"Hypothesis {i}",
            "candidate_actions": [],
            "reasoning": "Testing",
            "uncertainties": "None",
            "tags": []
        })

    # Test sampling mode
    history_tool = mcp._tool_manager._tools["get_thought_history_bucketed"]
    result = await history_tool.run(arguments={
        "hours": 1,
        "samples_per_hour": 6,
        "aggregation": "middle"
    })

    history = json.loads(result.content[0].text)

    # Should return sampled entries
    assert isinstance(history, list)
    assert len(history) > 0
    for entry in history:
        assert "timestamp" in entry
        assert "observation" in entry


@pytest.mark.asyncio
@freeze_time("2025-01-24 12:00:00")
async def test_get_thought_history_bucketed_count(setup_thinking_state):
    """Test get_thought_history_bucketed with count aggregation"""
    mcp = setup_thinking_state

    # Add test data
    base_time = datetime(2025, 1, 24, 11, 0, 0, tzinfo=timezone.utc)
    for i in range(3):
        thinking_module.thought_history.append({
            "timestamp": (base_time + timedelta(minutes=i)).isoformat(),
            "observation": "Test observation",
            "hypothesis": "Test hypothesis",
            "candidate_actions": [],
            "reasoning": "Testing",
            "uncertainties": "None",
            "tags": []
        })

    # Test count aggregation
    history_tool = mcp._tool_manager._tools["get_thought_history_bucketed"]
    result = await history_tool.run(arguments={
        "hours": 1,
        "samples_per_hour": 6,
        "aggregation": "count"
    })

    history = json.loads(result.content[0].text)

    # Should return bucket statistics
    assert isinstance(history, list)
    assert len(history) == 1  # All in one bucket
    assert history[0]["value"] == 3
    assert history[0]["count"] == 3

"""
Unit Tests for Action Log Module

These tests verify the action logging functionality including:
- Logging different action types
- Action type validation
- Retrieving recent actions
- Keyword searching
- State persistence and recovery
- Pagination
"""

import pytest
import pytest_asyncio
import json
from datetime import datetime, timedelta
from freezegun import freeze_time
from fastmcp import FastMCP
import tools.action_log as action_log_module
from tools.action_log import setup_action_log_tools
from pathlib import Path


@pytest_asyncio.fixture(autouse=True)
async def setup_action_log_state(tmp_path):
    """Reset action log state before each test"""
    # Use temp directory for state file (don't touch production state!)
    from utils.jsonl_history import JsonlHistory

    original_history = action_log_module.action_history

    # Create new history instance with temp file
    action_log_module.action_history = JsonlHistory(
        file_path=tmp_path / "action_log.jsonl",
        max_memory_entries=1000
    )

    # Create MCP instance and setup tools
    mcp = FastMCP("test")
    setup_action_log_tools(mcp)

    yield mcp

    # Restore original history
    action_log_module.action_history = original_history


@pytest.mark.asyncio
async def test_log_action_water(setup_action_log_state):
    """Test logging a water action"""
    mcp = setup_action_log_state
    log_action_tool = mcp._tool_manager._tools["log_action"]

    tool_result = await log_action_tool.run(arguments={
        "type": "water",
        "details": {
            "ml": 40,
            "reason": "Soil moisture dropped to 1200"
        }
    })
    result = json.loads(tool_result.content[0].text)

    assert result["success"] is True
    assert "timestamp" in result
    assert len(action_log_module.action_history) == 1

    # Verify stored action
    actions = action_log_module.action_history.get_all()
    assert len(actions) == 1
    action = actions[0]
    assert action["type"] == "water"
    assert action["details"]["ml"] == 40


@pytest.mark.asyncio
async def test_log_action_light(setup_action_log_state):
    """Test logging a light action"""
    mcp = setup_action_log_state
    log_action_tool = mcp._tool_manager._tools["log_action"]

    tool_result = await log_action_tool.run(arguments={
        "type": "light",
        "details": {
            "duration_minutes": 90,
            "reason": "Providing daily light exposure"
        }
    })
    result = json.loads(tool_result.content[0].text)

    assert result["success"] is True
    assert len(action_log_module.action_history) == 1

    actions = action_log_module.action_history.get_all()
    action = actions[0]
    assert action["type"] == "light"
    assert action["details"]["duration_minutes"] == 90


@pytest.mark.asyncio
async def test_log_action_observe(setup_action_log_state):
    """Test logging an observe action"""
    mcp = setup_action_log_state
    log_action_tool = mcp._tool_manager._tools["log_action"]

    tool_result = await log_action_tool.run(arguments={
        "type": "observe",
        "details": {
            "observation": "Plant leaves are slightly drooping",
            "photo_url": "http://example.com/photo.jpg"
        }
    })
    result = json.loads(tool_result.content[0].text)

    assert result["success"] is True
    actions = action_log_module.action_history.get_all()
    action = actions[0]
    assert action["type"] == "observe"
    assert "drooping" in action["details"]["observation"]


@pytest.mark.asyncio
async def test_log_action_alert(setup_action_log_state):
    """Test logging an alert action"""
    mcp = setup_action_log_state
    log_action_tool = mcp._tool_manager._tools["log_action"]

    tool_result = await log_action_tool.run(arguments={
        "type": "alert",
        "details": {
            "severity": "warning",
            "message": "Moisture sensor showing unusually low reading",
            "value": 800
        }
    })
    result = json.loads(tool_result.content[0].text)

    assert result["success"] is True
    actions = action_log_module.action_history.get_all()
    action = actions[0]
    assert action["type"] == "alert"
    assert action["details"]["severity"] == "warning"


@pytest.mark.asyncio
async def test_log_action_invalid_type(setup_action_log_state):
    """Test that invalid action types are rejected"""
    mcp = setup_action_log_state
    log_action_tool = mcp._tool_manager._tools["log_action"]

    # Invalid type should be caught by Pydantic validation
    with pytest.raises(Exception):  # Will be a Pydantic validation error
        await log_action_tool.run(arguments={
            "type": "invalid_type",
            "details": {}
        })


@pytest.mark.asyncio
async def test_log_action_invalid_details_structure(setup_action_log_state):
    """Test that invalid details structure is rejected"""
    mcp = setup_action_log_state
    log_action_tool = mcp._tool_manager._tools["log_action"]

    # Pass a string instead of a dict for details
    with pytest.raises(Exception):  # Will be a Pydantic validation error
        await log_action_tool.run(arguments={
            "type": "alert",
            "details": "this should be a dict"
        })


@pytest.mark.asyncio
async def test_get_recent_default(setup_action_log_state):
    """Test getting recent actions with default limit"""
    mcp = setup_action_log_state
    log_action_tool = mcp._tool_manager._tools["log_action"]
    get_recent_tool = mcp._tool_manager._tools["get_recent_actions"]

    # Log 10 actions
    for i in range(10):
        await log_action_tool.run(arguments={
            "type": "observe",
            "details": {"note": f"Action {i}"}
        })

    # Get recent (default 5)
    tool_result = await get_recent_tool.run(arguments={})
    result = json.loads(tool_result.content[0].text)

    assert result["count"] == 5
    assert len(result["actions"]) == 5
    # Should get the 5 most recent (5-9)
    assert result["actions"][0]["details"]["note"] == "Action 5"
    assert result["actions"][4]["details"]["note"] == "Action 9"


@pytest.mark.asyncio
async def test_get_recent_custom_limit(setup_action_log_state):
    """Test getting recent actions with custom limit"""
    mcp = setup_action_log_state
    log_action_tool = mcp._tool_manager._tools["log_action"]
    get_recent_tool = mcp._tool_manager._tools["get_recent_actions"]

    # Log 10 actions
    for i in range(10):
        await log_action_tool.run(arguments={
            "type": "observe",
            "details": {"note": f"Action {i}"}
        })

    # Get recent 3
    tool_result = await get_recent_tool.run(arguments={"n": 3})
    result = json.loads(tool_result.content[0].text)

    assert result["count"] == 3
    assert result["actions"][0]["details"]["note"] == "Action 7"
    assert result["actions"][2]["details"]["note"] == "Action 9"


@pytest.mark.asyncio
async def test_get_recent_pagination(setup_action_log_state):
    """Test pagination with offset"""
    mcp = setup_action_log_state
    log_action_tool = mcp._tool_manager._tools["log_action"]
    get_recent_tool = mcp._tool_manager._tools["get_recent_actions"]

    # Log 10 actions
    for i in range(10):
        await log_action_tool.run(arguments={
            "type": "observe",
            "details": {"note": f"Action {i}"}
        })

    # Get 3 actions with offset 5 (skip 5 most recent, get 3 before that)
    tool_result = await get_recent_tool.run(arguments={"n": 3, "offset": 5})
    result = json.loads(tool_result.content[0].text)

    assert result["count"] == 3
    # Should get entries 2, 3, 4
    assert result["actions"][0]["details"]["note"] == "Action 2"
    assert result["actions"][2]["details"]["note"] == "Action 4"


@pytest.mark.asyncio
async def test_search_keyword(setup_action_log_state):
    """Test searching for keywords in actions"""
    mcp = setup_action_log_state
    log_action_tool = mcp._tool_manager._tools["log_action"]
    search_tool = mcp._tool_manager._tools["search_actions"]

    # Log actions with different keywords
    await log_action_tool.run(arguments={
        "type": "water",
        "details": {"ml": 40, "reason": "Moisture level low"}
    })

    await log_action_tool.run(arguments={
        "type": "light",
        "details": {"duration_minutes": 90, "reason": "Daily light cycle"}
    })

    await log_action_tool.run(arguments={
        "type": "observe",
        "details": {"note": "Checking moisture sensor reading"}
    })

    # Search for "moisture"
    tool_result = await search_tool.run(arguments={"keyword": "moisture"})
    result = json.loads(tool_result.content[0].text)

    assert result["count"] == 2  # Found in water and observe actions


@pytest.mark.asyncio
async def test_search_case_insensitive(setup_action_log_state):
    """Test that search is case-insensitive"""
    mcp = setup_action_log_state
    log_action_tool = mcp._tool_manager._tools["log_action"]
    search_tool = mcp._tool_manager._tools["search_actions"]

    await log_action_tool.run(arguments={
        "type": "water",
        "details": {"reason": "MOISTURE LEVEL LOW"}
    })

    # Search with lowercase
    tool_result = await search_tool.run(arguments={"keyword": "moisture"})
    result = json.loads(tool_result.content[0].text)

    assert result["count"] == 1


@pytest.mark.asyncio
async def test_search_time_window(setup_action_log_state):
    """Test search respects time window"""
    mcp = setup_action_log_state
    log_action_tool = mcp._tool_manager._tools["log_action"]
    search_tool = mcp._tool_manager._tools["search_actions"]

    base_time = datetime.now()

    # Log action 30 hours ago
    with freeze_time(base_time - timedelta(hours=30)):
        await log_action_tool.run(arguments={
            "type": "water",
            "details": {"note": "Old watering"}
        })

    # Log action 10 hours ago
    with freeze_time(base_time - timedelta(hours=10)):
        await log_action_tool.run(arguments={
            "type": "water",
            "details": {"note": "Recent watering"}
        })

    # Search for "watering" in last 24 hours
    with freeze_time(base_time):
        tool_result = await search_tool.run(arguments={"keyword": "watering", "hours": 24})
        result = json.loads(tool_result.content[0].text)

    assert result["count"] == 1  # Only the recent one
    assert "Recent" in result["actions"][0]["details"]["note"]


@pytest.mark.asyncio
async def test_state_persistence(setup_action_log_state):
    """Test that actions are persisted to disk"""
    mcp = setup_action_log_state
    log_action_tool = mcp._tool_manager._tools["log_action"]

    # Log an action
    await log_action_tool.run(arguments={
        "type": "water",
        "details": {"ml": 50, "reason": "Test watering"}
    })

    # Verify file was created
    assert action_log_module.action_history.file_path.exists()

    # Read the file
    with open(action_log_module.action_history.file_path, 'r') as f:
        lines = f.readlines()

    assert len(lines) == 1
    stored = json.loads(lines[0])
    assert stored["type"] == "water"
    assert stored["details"]["ml"] == 50


@pytest.mark.asyncio
async def test_state_recovery(setup_action_log_state):
    """Test that state is recovered from disk on restart"""
    mcp = setup_action_log_state
    log_action_tool = mcp._tool_manager._tools["log_action"]
    get_recent_tool = mcp._tool_manager._tools["get_recent_actions"]

    # Log some actions
    for i in range(3):
        await log_action_tool.run(arguments={
            "type": "observe",
            "details": {"note": f"Action {i}"}
        })

    # Clear memory (simulating restart) and create new instance
    file_path = action_log_module.action_history.file_path
    from utils.jsonl_history import JsonlHistory
    action_log_module.action_history = JsonlHistory(file_path=file_path, max_memory_entries=1000)

    # Query should trigger state load
    tool_result = await get_recent_tool.run(arguments={"n": 5})
    result = json.loads(tool_result.content[0].text)

    assert result["count"] == 3
    assert result["actions"][0]["details"]["note"] == "Action 0"


@pytest.mark.asyncio
async def test_memory_pruning(setup_action_log_state):
    """Test that memory is pruned to MAX_MEMORY_ENTRIES"""
    mcp = setup_action_log_state
    log_action_tool = mcp._tool_manager._tools["log_action"]

    # Temporarily set a low max for testing
    original_max = action_log_module.action_history.max_memory_entries
    action_log_module.action_history.max_memory_entries = 5

    # Log 10 actions
    for i in range(10):
        await log_action_tool.run(arguments={
            "type": "observe",
            "details": {"note": f"Action {i}"}
        })

    # Memory should be pruned to 5
    assert len(action_log_module.action_history) == 5
    # Should keep the most recent 5 (5-9)
    all_actions = action_log_module.action_history.get_all()
    assert all_actions[0]["details"]["note"] == "Action 5"

    # Restore original max
    action_log_module.action_history.max_memory_entries = original_max


@pytest.mark.asyncio
async def test_get_recent_empty(setup_action_log_state):
    """Test getting recent actions when none exist"""
    mcp = setup_action_log_state
    get_recent_tool = mcp._tool_manager._tools["get_recent_actions"]

    tool_result = await get_recent_tool.run(arguments={})
    result = json.loads(tool_result.content[0].text)

    assert result["count"] == 0
    assert result["actions"] == []


@pytest.mark.asyncio
async def test_search_no_results(setup_action_log_state):
    """Test search when no results match"""
    mcp = setup_action_log_state
    log_action_tool = mcp._tool_manager._tools["log_action"]
    search_tool = mcp._tool_manager._tools["search_actions"]

    await log_action_tool.run(arguments={
        "type": "water",
        "details": {"ml": 40}
    })

    tool_result = await search_tool.run(arguments={"keyword": "nonexistent"})
    result = json.loads(tool_result.content[0].text)

    assert result["count"] == 0
    assert result["actions"] == []


@pytest.mark.asyncio
async def test_mixed_action_types(setup_action_log_state):
    """Test logging and retrieving mixed action types"""
    mcp = setup_action_log_state
    log_action_tool = mcp._tool_manager._tools["log_action"]
    get_recent_tool = mcp._tool_manager._tools["get_recent_actions"]

    # Log different types
    await log_action_tool.run(arguments={
        "type": "water",
        "details": {"ml": 40}
    })

    await log_action_tool.run(arguments={
        "type": "light",
        "details": {"duration_minutes": 90}
    })

    await log_action_tool.run(arguments={
        "type": "observe",
        "details": {"note": "Plant looks healthy"}
    })

    await log_action_tool.run(arguments={
        "type": "alert",
        "details": {"severity": "info", "message": "System check"}
    })

    # Get all recent
    tool_result = await get_recent_tool.run(arguments={"n": 10})
    result = json.loads(tool_result.content[0].text)

    assert result["count"] == 4
    types = [a["type"] for a in result["actions"]]
    assert "water" in types
    assert "light" in types
    assert "observe" in types
    assert "alert" in types

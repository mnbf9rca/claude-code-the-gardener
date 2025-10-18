"""
Unit Tests for Camera Module

These tests verify the camera functionality including:
- Photo capture
- URL generation
- History tracking
"""
import pytest
import pytest_asyncio
import json
from datetime import datetime
from freezegun import freeze_time
from fastmcp import FastMCP
import tools.camera as camera_module
from tools.camera import setup_camera_tools
from shared_state import reset_cycle, current_cycle_status


@pytest_asyncio.fixture(autouse=True)
async def setup_camera_state():
    """Reset camera state before each test"""
    # Reset cycle state
    reset_cycle()
    current_cycle_status["written"] = True  # Allow tool calls

    # Clear photo history
    camera_module.photo_history.clear()

    # Create MCP instance and setup tools
    mcp = FastMCP("test")
    setup_camera_tools(mcp)

    yield mcp

    # Cleanup
    camera_module.photo_history.clear()


@pytest.mark.asyncio
async def test_capture_basic(setup_camera_state):
    """Test basic photo capture"""
    mcp = setup_camera_state
    capture_tool = mcp._tool_manager._tools["capture"]

    tool_result = await capture_tool.run(arguments={})
    result = json.loads(tool_result.content[0].text)

    assert "url" in result
    assert "timestamp" in result
    assert result["url"].startswith("http://192.168.1.100/photos/")
    assert result["url"].endswith(".jpg")
    assert len(camera_module.photo_history) == 1


@pytest.mark.asyncio
async def test_capture_unique_urls(setup_camera_state):
    """Test that each capture generates a unique URL"""
    mcp = setup_camera_state
    capture_tool = mcp._tool_manager._tools["capture"]

    # Capture multiple photos
    urls = []
    for _ in range(3):
        tool_result = await capture_tool.run(arguments={})
        result = json.loads(tool_result.content[0].text)
        urls.append(result["url"])

    # All URLs should be unique
    assert len(set(urls)) == 3


@pytest.mark.asyncio
async def test_capture_timestamp_format(setup_camera_state):
    """Test that timestamps are properly formatted in URLs"""
    mcp = setup_camera_state
    capture_tool = mcp._tool_manager._tools["capture"]

    with freeze_time("2024-01-01 12:34:56.789"):
        tool_result = await capture_tool.run(arguments={})
        result = json.loads(tool_result.content[0].text)

        # URL should have timestamp with special chars replaced
        assert "2024-01-01" in result["url"]
        assert "12-34-56" in result["url"]
        # Check ISO timestamp is valid
        datetime.fromisoformat(result["timestamp"])


@pytest.mark.asyncio
async def test_photo_history_storage(setup_camera_state):
    """Test that photo history is properly maintained"""
    mcp = setup_camera_state
    capture_tool = mcp._tool_manager._tools["capture"]

    # Capture multiple photos
    for _ in range(5):
        await capture_tool.run(arguments={})

    assert len(camera_module.photo_history) == 5

    # Check history structure
    for entry in camera_module.photo_history:
        assert "url" in entry
        assert "timestamp" in entry
        assert entry["url"].startswith("http://192.168.1.100/photos/")


@pytest.mark.asyncio
@pytest.mark.parametrize("num_photos,limit,expected_count", [
    (0, None, 0),  # Empty history, default limit
    (3, None, 3),  # 3 photos, default limit (5)
    (3, 2, 2),     # 3 photos, limit 2
    (10, 5, 5),    # 10 photos, limit 5
])
async def test_get_recent_photos(setup_camera_state, num_photos, limit, expected_count):
    """Test getting recent photo URLs with various scenarios"""
    mcp = setup_camera_state
    capture_tool = mcp._tool_manager._tools["capture"]
    recent_tool = mcp._tool_manager._tools["get_recent_photos"]

    # Capture the specified number of photos
    captured_urls = []
    for _ in range(num_photos):
        tool_result = await capture_tool.run(arguments={})
        capture_result = json.loads(tool_result.content[0].text)
        captured_urls.append(capture_result["url"])

    # Get recent photos with specified limit
    args = {"limit": limit} if limit else {}
    tool_result = await recent_tool.run(arguments=args)

    # Check results based on expected count
    if expected_count == 0:
        assert tool_result.content == []
    else:
        result = json.loads(tool_result.content[0].text)
        assert len(result) == expected_count
        assert all("url" in photo and "timestamp" in photo for photo in result)

        # Verify we got the most recent ones
        if limit and limit < num_photos:
            expected_urls = captured_urls[-limit:]
            actual_urls = [photo["url"] for photo in result]
            assert actual_urls == expected_urls


@pytest.mark.asyncio
async def test_recent_photos_limit_validation(setup_camera_state):
    """Test that get_recent_photos limit is validated"""
    mcp = setup_camera_state
    recent_tool = mcp._tool_manager._tools["get_recent_photos"]

    # Capture many photos
    capture_tool = mcp._tool_manager._tools["capture"]
    for _ in range(25):
        await capture_tool.run(arguments={})

    # Test maximum limit (20)
    tool_result = await recent_tool.run(arguments={"limit": 20})
    result = json.loads(tool_result.content[0].text)
    assert len(result) == 20

    # Test that limit above 20 is rejected
    with pytest.raises(Exception):  # Pydantic validation error
        await recent_tool.run(arguments={"limit": 25})

    # Test that limit below 1 is rejected
    with pytest.raises(Exception):  # Pydantic validation error
        await recent_tool.run(arguments={"limit": 0})


@pytest.mark.asyncio
async def test_history_limit(setup_camera_state):
    """Test that history is limited to prevent memory issues"""
    mcp = setup_camera_state
    capture_tool = mcp._tool_manager._tools["capture"]

    # Capture more than the limit (100)
    for _ in range(105):
        await capture_tool.run(arguments={})

    # History should be capped at 100
    assert len(camera_module.photo_history) == 100


@pytest.mark.asyncio
async def test_gatekeeper_enforcement(setup_camera_state):
    """Test that plant status must be written first"""
    mcp = setup_camera_state
    capture_tool = mcp._tool_manager._tools["capture"]

    # Reset the cycle status
    current_cycle_status["written"] = False

    with pytest.raises(ValueError, match="Must call write_status first"):
        await capture_tool.run(arguments={})


@pytest.mark.asyncio
async def test_photo_history_order(setup_camera_state):
    """Test that photo history maintains chronological order"""
    mcp = setup_camera_state
    capture_tool = mcp._tool_manager._tools["capture"]

    with freeze_time("2024-01-01 12:00:00") as frozen_time:
        # Capture photos at different times
        await capture_tool.run(arguments={})
        frozen_time.move_to("2024-01-01 12:05:00")
        await capture_tool.run(arguments={})
        frozen_time.move_to("2024-01-01 12:10:00")
        await capture_tool.run(arguments={})

    # Verify chronological order
    timestamps = [datetime.fromisoformat(p["timestamp"]) for p in camera_module.photo_history]
    assert timestamps == sorted(timestamps)
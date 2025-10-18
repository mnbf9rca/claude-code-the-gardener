"""
Unit Tests for Camera Module

These tests verify the camera functionality including:
- Photo capture
- URL generation
- History tracking
"""
import os
import json
import shutil
import tempfile
from pathlib import Path
from datetime import datetime

import pytest
import pytest_asyncio
from freezegun import freeze_time
from fastmcp import FastMCP

import tools.camera as camera_module
from tools.camera import setup_camera_tools
from shared_state import reset_cycle, current_cycle_status


@pytest_asyncio.fixture(autouse=True)
async def setup_camera_state():
    """Reset camera state before each test and ensure proper cleanup"""
    # Save original environment
    original_env = {
        "CAMERA_ENABLED": os.environ.get("CAMERA_ENABLED"),
        "CAMERA_SAVE_PATH": os.environ.get("CAMERA_SAVE_PATH"),
    }

    # Create temp directory for test photos
    temp_dir = tempfile.mkdtemp(prefix="test_photos_")
    os.environ["CAMERA_SAVE_PATH"] = temp_dir

    # Keep camera enabled to test real functionality if available
    # Tests will work with either real or mock camera
    if original_env["CAMERA_ENABLED"] is None:
        os.environ["CAMERA_ENABLED"] = "true"

    # Force reload of camera configuration
    from dotenv import load_dotenv
    load_dotenv()

    # Update camera config
    camera_module.CAMERA_CONFIG["save_path"] = Path(temp_dir)
    camera_module.CAMERA_CONFIG["enabled"] = os.getenv("CAMERA_ENABLED", "true").lower() == "true"

    # Reset camera state
    camera_module.camera = None
    camera_module.camera_available = False

    # Reset cycle state
    reset_cycle()
    current_cycle_status["written"] = True  # Allow tool calls

    # Clear photo history
    camera_module.photo_history.clear()

    # Create MCP instance and setup tools
    mcp = FastMCP("test")
    setup_camera_tools(mcp)

    yield mcp

    # === CLEANUP ===

    # Clean up camera resources
    camera_module.cleanup_camera()
    camera_module.photo_history.clear()

    # Clean up test photos
    if Path(temp_dir).exists():
        photo_files = list(Path(temp_dir).glob("*.jpg"))
        photo_count = len(photo_files)
        if photo_count > 0:
            print(f"\n  Cleaned up {photo_count} test photos")
        shutil.rmtree(temp_dir)

    # Restore original environment
    for key, value in original_env.items():
        if value is not None:
            os.environ[key] = value
        else:
            os.environ.pop(key, None)


@pytest.mark.asyncio
async def test_capture_basic(setup_camera_state):
    """Test basic photo capture"""
    mcp = setup_camera_state
    capture_tool = mcp._tool_manager._tools["capture"]

    tool_result = await capture_tool.run(arguments={})
    result = json.loads(tool_result.content[0].text)

    assert "url" in result
    assert "timestamp" in result
    assert "mode" in result
    assert "success" in result
    assert result["success"] is True
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
    """Test that timestamps are properly formatted"""
    mcp = setup_camera_state
    capture_tool = mcp._tool_manager._tools["capture"]

    with freeze_time("2024-01-01 12:34:56.789"):
        tool_result = await capture_tool.run(arguments={})
        result = json.loads(tool_result.content[0].text)

        # Check ISO timestamp is valid
        datetime.fromisoformat(result["timestamp"])
        assert result["timestamp"].startswith("2024-12-31")

        url = result["url"]
        assert "2024" in url and ("1231" in url or "12-31" in url)


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
        assert "mode" in entry
        assert entry["url"].endswith(".jpg")


@pytest.mark.asyncio
async def test_get_recent_photos_empty(setup_camera_state):
    """Test getting recent photos when history is empty"""
    mcp = setup_camera_state
    recent_tool = mcp._tool_manager._tools["get_recent_photos"]

    tool_result = await recent_tool.run(arguments={})
    assert tool_result.content == []


@pytest.mark.asyncio
@pytest.mark.parametrize("num_photos,limit,args,expected_count", [
    (3, "default", {}, 3),           # 3 photos, default limit
    (3, 2, {"limit": 2}, 2),         # 3 photos, limit 2
    (10, 5, {"limit": 5}, 5),        # 10 photos, limit 5
])
async def test_get_recent_photos_with_data(setup_camera_state, num_photos, limit, args, expected_count):
    """Test getting recent photo URLs with various limits"""
    mcp = setup_camera_state
    capture_tool = mcp._tool_manager._tools["capture"]
    recent_tool = mcp._tool_manager._tools["get_recent_photos"]

    # Capture the specified number of photos
    captured_urls = []
    for _ in range(num_photos):
        tool_result = await capture_tool.run(arguments={})
        capture_result = json.loads(tool_result.content[0].text)
        captured_urls.append(capture_result["url"])

    # Get recent photos with specified arguments
    tool_result = await recent_tool.run(arguments=args)

    result = json.loads(tool_result.content[0].text)
    assert len(result) == expected_count
    assert all("url" in photo and "timestamp" in photo and "mode" in photo for photo in result)

    # For tests with explicit limits less than total photos, verify order
    expected_urls = captured_urls[-expected_count:]
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
async def test_camera_status(setup_camera_state):
    """Test camera status reporting"""
    mcp = setup_camera_state
    status_tool = mcp._tool_manager._tools["get_camera_status"]

    tool_result = await status_tool.run(arguments={})
    status = json.loads(tool_result.content[0].text)

    # Required fields
    assert "opencv_available" in status
    assert "camera_enabled" in status
    assert "camera_available" in status
    assert "mode" in status
    assert "save_path" in status
    assert "resolution" in status

    # Mode should be either "real" or "mock"
    assert status["mode"] in ["real", "mock"]

    # camera_available should always be a boolean
    assert isinstance(status["camera_available"], bool)


@pytest.mark.asyncio
async def test_capture_returns_valid_response(setup_camera_state):
    """Test that capture always returns a valid response"""
    mcp = setup_camera_state
    capture_tool = mcp._tool_manager._tools["capture"]

    tool_result = await capture_tool.run(arguments={})
    result = json.loads(tool_result.content[0].text)

    # Should always have these fields regardless of mode
    assert result["success"] is True
    assert result["url"].endswith(".jpg")
    assert len(result["url"]) > 10  # Not empty or too short
    assert result["mode"] in ["real", "mock"]
    assert "timestamp" in result
    assert datetime.fromisoformat(result["timestamp"])  # Valid timestamp


@pytest.mark.asyncio
async def test_capture_mode_matches_config(setup_camera_state):
    """Test that capture mode matches camera configuration"""
    mcp = setup_camera_state
    status_tool = mcp._tool_manager._tools["get_camera_status"]
    capture_tool = mcp._tool_manager._tools["capture"]

    # Get status
    tool_result = await status_tool.run(arguments={})
    status = json.loads(tool_result.content[0].text)

    # Capture a photo
    tool_result = await capture_tool.run(arguments={})
    result = json.loads(tool_result.content[0].text)

    # Mode should match what status reported
    assert result["mode"] == status["mode"]


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
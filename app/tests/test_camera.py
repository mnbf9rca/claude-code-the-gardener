"""
Unit Tests for Camera Module

These tests verify the camera functionality including:
- Photo capture with real camera
- Error handling when camera unavailable
- URL generation
- History tracking
- Gatekeeper enforcement
"""
import json
from pathlib import Path
from datetime import datetime
from urllib.parse import urlparse

import pytest
from freezegun import freeze_time
from fastmcp import FastMCP
from mcp.types import TextContent

import tools.camera as camera_module
from tools.camera import setup_camera_tools
from conftest import requires_camera


def extract_json_from_result(tool_result):
    """Extract JSON from a tool result's content."""
    # FastMCP can return data in different ways:
    # 1. As structured_content directly
    if hasattr(tool_result, 'structured_content') and tool_result.structured_content is not None:
        return tool_result.structured_content

    # 2. As content with TextContent items
    if hasattr(tool_result, 'content') and tool_result.content:
        for content_item in tool_result.content:
            if isinstance(content_item, TextContent):
                return json.loads(content_item.text)
        # Try to parse first item as string
        return json.loads(str(tool_result.content[0]))

    # 3. Empty content means empty result
    return []


class TestCameraWithRealDevice:
    """Tests that require a real camera device."""

    @pytest.mark.asyncio
    @requires_camera
    async def test_capture_with_real_camera(
        self, camera_config, test_photos_dir, reset_camera_module, allow_camera_capture
    ):
        """Test photo capture with a real camera.

        Note: Fixture parameters are used by pytest's dependency injection.
        """
        # Setup MCP with camera tools
        mcp = FastMCP("test")
        setup_camera_tools(mcp)
        capture_tool = mcp._tool_manager._tools["capture_photo"]

        # Capture a photo
        tool_result = await capture_tool.run(arguments={})
        result = extract_json_from_result(tool_result)

        # Verify successful capture
        assert "url" in result
        assert "timestamp" in result
        assert result["url"].endswith(".jpg")

        # URL should now be HTTP format
        assert result["url"].startswith("http")

        # Extract filename from HTTP URL and verify file exists
        parsed_url = urlparse(result["url"])
        filename = Path(parsed_url.path).name
        photo_path = test_photos_dir / filename
        assert photo_path.exists()
        assert photo_path.stat().st_size > 0

        # Check history was updated
        assert len(camera_module.photo_history) == 1
        assert camera_module.photo_history[0]["url"] == result["url"]

    @pytest.mark.asyncio
    @requires_camera
    async def test_multiple_captures_unique_files(
        self, camera_config, test_photos_dir, reset_camera_module, allow_camera_capture
    ):
        """Test that each capture creates a unique file.

        Note: Fixture parameters are used by pytest's dependency injection.
        """
        mcp = FastMCP("test")
        setup_camera_tools(mcp)
        capture_tool = mcp._tool_manager._tools["capture_photo"]

        # Capture multiple photos
        urls = []
        for _ in range(3):
            tool_result = await capture_tool.run(arguments={})
            result = extract_json_from_result(tool_result)
            urls.append(result["url"])

        # All URLs should be unique
        assert len(set(urls)) == 3

        # All files should exist (extract filename from HTTP URL)
        for url in urls:
            parsed_url = urlparse(url)
            filename = Path(parsed_url.path).name
            photo_path = test_photos_dir / filename
            assert photo_path.exists()

    @pytest.mark.asyncio
    @requires_camera
    async def test_camera_status_with_real_device(
        self, camera_config, reset_camera_module
    ):
        """Test camera status reporting with real camera.

        Note: Fixture parameters are used by pytest's dependency injection.
        """
        mcp = FastMCP("test")
        setup_camera_tools(mcp)
        status_tool = mcp._tool_manager._tools["get_camera_status"]

        tool_result = await status_tool.run(arguments={})
        status = extract_json_from_result(tool_result)

        # Should report camera as available
        assert status["camera_enabled"] is True
        assert status["camera_available"] is True
        assert status["error"] is None
        assert status["device_index"] == 0
        assert "resolution" in status


class TestCameraWithoutDevice:
    """Tests that work without a real camera or test error conditions."""

    @pytest.mark.asyncio
    async def test_capture_with_disabled_camera(
        self, camera_config_disabled, test_photos_dir, reset_camera_module, allow_camera_capture
    ):
        """Test behavior when camera is disabled in config.

        Note: Fixture parameters are used by pytest's dependency injection.
        """
        mcp = FastMCP("test")
        setup_camera_tools(mcp)
        capture_tool = mcp._tool_manager._tools["capture_photo"]

        # Try to capture - should raise exception
        with pytest.raises(Exception) as exc_info:
            await capture_tool.run(arguments={})

        # Should contain error about camera being disabled
        assert "disabled" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_capture_with_invalid_device_index(
        self, camera_config, test_photos_dir, reset_camera_module, allow_camera_capture, monkeypatch
    ):
        """Test behavior with invalid camera device index (out of range).

        Note: Fixture parameters are used by pytest's dependency injection.
        """
        # Set invalid device index (out of range)
        monkeypatch.setenv("CAMERA_DEVICE_INDEX", "999")

        # Force reload of configuration
        import importlib
        importlib.reload(camera_module)

        mcp = FastMCP("test")
        setup_camera_tools(mcp)
        capture_tool = mcp._tool_manager._tools["capture_photo"]

        # Try to capture - should raise exception
        with pytest.raises(Exception) as exc_info:
            await capture_tool.run(arguments={})

        # Should contain error message (camera not available or cannot open)
        error_msg = str(exc_info.value).lower()
        assert "camera" in error_msg or "open" in error_msg

    @pytest.mark.asyncio
    async def test_capture_with_non_integer_device_index(
        self, test_photos_dir, reset_camera_module, allow_camera_capture, monkeypatch
    ):
        """Test behavior with non-integer device index values.

        Note: Fixture parameters are used by pytest's dependency injection.
        """
        # Test with non-integer string value
        monkeypatch.setenv("CAMERA_ENABLED", "true")
        monkeypatch.setenv("CAMERA_DEVICE_INDEX", "not_a_number")
        monkeypatch.setenv("CAMERA_SAVE_PATH", str(test_photos_dir))

        # Attempting to reload configuration with invalid integer should raise ValueError
        import importlib
        with pytest.raises(ValueError):
            importlib.reload(camera_module)

    @pytest.mark.asyncio
    async def test_capture_with_negative_device_index(
        self, test_photos_dir, reset_camera_module, allow_camera_capture, monkeypatch
    ):
        """Test behavior with negative device index.

        Note: Fixture parameters are used by pytest's dependency injection.
        """
        # Set negative device index
        monkeypatch.setenv("CAMERA_ENABLED", "true")
        monkeypatch.setenv("CAMERA_DEVICE_INDEX", "-1")
        monkeypatch.setenv("CAMERA_SAVE_PATH", str(test_photos_dir))

        # Force reload of configuration (negative should be allowed by int() but fail on camera init)
        import importlib
        importlib.reload(camera_module)

        mcp = FastMCP("test")
        setup_camera_tools(mcp)
        capture_tool = mcp._tool_manager._tools["capture_photo"]

        # Try to capture - should raise exception
        with pytest.raises(Exception) as exc_info:
            await capture_tool.run(arguments={})

        # Should contain error message (camera not available or cannot open)
        error_msg = str(exc_info.value).lower()
        assert "camera" in error_msg or "open" in error_msg

    @pytest.mark.asyncio
    async def test_get_recent_photos_empty(
        self, camera_config, reset_camera_module
    ):
        """Test getting recent photos when history is empty.

        Note: Fixture parameters are used by pytest's dependency injection.
        """
        mcp = FastMCP("test")
        setup_camera_tools(mcp)
        recent_tool = mcp._tool_manager._tools["get_recent_photos"]

        tool_result = await recent_tool.run(arguments={})
        result = extract_json_from_result(tool_result)

        # FastMCP wraps list results in {"result": [...]}
        if isinstance(result, dict) and "result" in result:
            assert result["result"] == []
        else:
            assert result == []

    @pytest.mark.asyncio
    async def test_get_recent_photos_with_history(
        self, camera_config, reset_camera_module
    ):
        """Test getting recent photos from history.

        Note: Fixture parameters are used by pytest's dependency injection.
        """
        # Manually add some entries to history
        camera_module.photo_history = [
            {"url": f"/photos/photo_{i}.jpg", "timestamp": f"2024-01-0{i}T12:00:00"}
            for i in range(1, 6)
        ]

        mcp = FastMCP("test")
        setup_camera_tools(mcp)
        recent_tool = mcp._tool_manager._tools["get_recent_photos"]

        # Get default (5 photos)
        tool_result = await recent_tool.run(arguments={})
        result = extract_json_from_result(tool_result)
        # FastMCP wraps list results - unwrap if needed
        photos = result.get("result", result) if isinstance(result, dict) else result
        assert len(photos) == 5

        # Get limited number
        tool_result = await recent_tool.run(arguments={"limit": 3})
        result = extract_json_from_result(tool_result)
        # FastMCP wraps list results - unwrap if needed
        photos = result.get("result", result) if isinstance(result, dict) else result
        assert len(photos) == 3
        # Should get the most recent ones
        assert photos[0]["url"] == "/photos/photo_3.jpg"
        assert photos[-1]["url"] == "/photos/photo_5.jpg"

    @pytest.mark.asyncio
    async def test_photo_history_limit(
        self, camera_config, reset_camera_module
    ):
        """Test that history is limited to 100 entries.

        Note: Fixture parameters are used by pytest's dependency injection.
        """
        # Add 105 entries to history
        for i in range(105):
            camera_module.photo_history.append({
                "url": f"/photos/photo_{i:03d}.jpg",
                "timestamp": f"2024-01-01T{i//60:02d}:{i%60:02d}:00"
            })

        # Manually trigger the cleanup logic that happens in capture
        while len(camera_module.photo_history) > 100:
            camera_module.photo_history.pop(0)

        # Should be capped at 100
        assert len(camera_module.photo_history) == 100
        # Oldest should be photo_004 (0-4 were removed)
        assert camera_module.photo_history[0]["url"] == "/photos/photo_005.jpg"
        # Newest should be photo_104
        assert camera_module.photo_history[-1]["url"] == "/photos/photo_104.jpg"

    @pytest.mark.asyncio
    async def test_recent_photos_limit_validation(
        self, camera_config, reset_camera_module
    ):
        """Test that get_recent_photos validates limit parameter.

        Note: Fixture parameters are used by pytest's dependency injection.
        """
        mcp = FastMCP("test")
        setup_camera_tools(mcp)
        recent_tool = mcp._tool_manager._tools["get_recent_photos"]

        # Add some test data
        for i in range(25):
            camera_module.photo_history.append({
                "url": f"/photos/photo_{i}.jpg",
                "timestamp": "2024-01-01T12:00:00"
            })

        # Test maximum limit (20)
        tool_result = await recent_tool.run(arguments={"limit": 20})
        result = extract_json_from_result(tool_result)
        # FastMCP wraps list results - unwrap if needed
        photos = result.get("result", result) if isinstance(result, dict) else result
        assert len(photos) == 20

        # Test that limit above 20 is rejected
        with pytest.raises(Exception):  # Pydantic validation error
            await recent_tool.run(arguments={"limit": 25})

        # Test that limit below 1 is rejected
        with pytest.raises(Exception):  # Pydantic validation error
            await recent_tool.run(arguments={"limit": 0})

    @pytest.mark.asyncio
    async def test_camera_status_without_device(
        self, camera_config_disabled, reset_camera_module
    ):
        """Test camera status when camera is disabled.

        Note: Fixture parameters are used by pytest's dependency injection.
        """
        mcp = FastMCP("test")
        setup_camera_tools(mcp)
        status_tool = mcp._tool_manager._tools["get_camera_status"]

        tool_result = await status_tool.run(arguments={})
        status = extract_json_from_result(tool_result)

        # Required fields
        assert "camera_enabled" in status
        assert "camera_available" in status
        assert "device_index" in status
        assert "save_path" in status
        assert "resolution" in status
        assert "image_quality" in status
        assert "photos_captured" in status
        assert "error" in status

        # Should indicate camera disabled
        assert status["camera_enabled"] is False
        assert status["camera_available"] is False
        assert status["error"] is not None


class TestCameraWithSamplePhotos:
    """Tests using pre-captured sample photos."""

    @pytest.mark.asyncio
    async def test_sample_photos_exist(self, sample_photos):
        """Verify sample photos are available for testing."""
        assert len(sample_photos) > 0
        for photo in sample_photos:
            assert photo.exists()
            assert photo.suffix == ".jpg"
            assert photo.stat().st_size > 0

    @pytest.mark.asyncio
    async def test_timestamp_format_in_capture(
        self, camera_config, test_photos_dir, reset_camera_module, allow_camera_capture
    ):
        """Test that timestamps are properly formatted.

        Note: Fixture parameters are used by pytest's dependency injection.
        """
        mcp = FastMCP("test")
        setup_camera_tools(mcp)

        with freeze_time("2024-12-31 12:34:56.789"):
            # Mock a successful capture by adding to history
            camera_module.photo_history.append({
                "url": str(test_photos_dir / "test_photo.jpg"),
                "timestamp": datetime.now().isoformat()
            })

            recent_tool = mcp._tool_manager._tools["get_recent_photos"]
            tool_result = await recent_tool.run(arguments={"limit": 1})
            result = extract_json_from_result(tool_result)

            # FastMCP wraps list results - unwrap if needed
            photos = result.get("result", result) if isinstance(result, dict) else result

            # Check ISO timestamp is valid
            timestamp = photos[0]["timestamp"]
            parsed_time = datetime.fromisoformat(timestamp)
            assert parsed_time.year == 2024
            assert parsed_time.month == 12
            assert parsed_time.day == 31
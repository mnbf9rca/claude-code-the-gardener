#!/usr/bin/env python
"""
MANUAL CAMERA CHECK UTILITY
===========================

This is NOT a pytest test file - it's a standalone diagnostic utility.

Purpose:
--------
This script helps diagnose and verify camera hardware configuration for the
plant monitoring system. It performs real camera operations to test if your
USB camera is properly detected and working with the current configuration.

When to use:
-----------
- Initial camera setup on new hardware (Raspberry Pi, Mac, etc.)
- Debugging camera connection issues
- Verifying camera configuration changes
- Testing after system updates or hardware changes

How to run:
----------
From the app directory:
    uv run python camera_manual_check.py

The script will:
1. Check camera status and availability
2. Attempt to capture a real photo
3. Display diagnostic information
4. Show recent photo history

Configuration:
-------------
Edit the environment variables below to test different settings:
- CAMERA_DEVICE_INDEX: Camera device number (0, 1, 2...)
- CAMERA_SAVE_PATH: Where to save test photos

Note: This file is intentionally named without 'test_' prefix to prevent
pytest from discovering and running it during automated test suites.
"""
import asyncio
import json
import os
import sys
from pathlib import Path

# Add parent (app) directory to path so we can import server and utils
sys.path.insert(0, str(Path(__file__).parent.parent))

# Set up test environment - EDIT THESE TO TEST DIFFERENT CONFIGURATIONS
os.environ["CAMERA_ENABLED"] = "true"
os.environ["CAMERA_DEVICE_INDEX"] = "0"  # Try 0, 1, or 2 if camera not found
os.environ["CAMERA_SAVE_PATH"] = "./test_photos"  # Directory for test captures

from server import mcp
from utils.shared_state import reset_cycle, current_cycle_status

def extract_tool_result(result):
    """Extract data from MCP tool result (handles different formats)"""
    from mcp.types import TextContent

    if hasattr(result, 'structured_content') and result.structured_content:
        return result.structured_content

    # Try to parse from content
    for content_item in result.content:
        if isinstance(content_item, TextContent):
            return json.loads(content_item.text)

    return None


async def check_status():
    """Check camera status and display results"""
    if not (status_tool := mcp._tool_manager._tools.get("get_camera_status")):
        return

    print("\n1. Checking camera status...")
    result = await status_tool.run(arguments={})
    status = extract_tool_result(result)

    print(json.dumps(status, indent=2))

    if not status.get("camera_available"):
        print("\n⚠️  Camera not detected.")
        if error := status.get("error"):
            print(f"   Error: {error}")
        print("   Try different CAMERA_DEVICE_INDEX (0, 1, 2...)")
        print("   On Mac: Built-in camera is usually 0")
        print("   On RPi: USB camera usually at /dev/video0 (index 0)")


async def check_capture():
    """Test photo capture and display results"""
    if not (capture_tool := mcp._tool_manager._tools.get("capture_photo")):
        return

    print("\n2. Testing photo capture...")
    try:
        result = await capture_tool.run(arguments={})
        photo = extract_tool_result(result)

        print(f"   Success: {photo['success']}")

        if photo['success']:
            photo_url = photo['url']
            print(f"   HTTP URL: {photo_url}")

            # Extract filename from URL and construct local path
            filename = photo_url.split('/')[-1]
            save_path = os.environ.get("CAMERA_SAVE_PATH", "./test_photos")
            local_path = Path(save_path) / filename

            print(f"   Local path: {local_path}")
            print(f"\n✅ Camera capture successful!")

            if local_path.exists():
                file_size = local_path.stat().st_size / 1024
                print(f"   File size: {file_size:.1f} KB")
            else:
                print(f"   ⚠️  Warning: File not found at {local_path}")
        else:
            print(f"\n⚠️  Capture failed: {photo.get('error', 'Unknown error')}")

    except Exception as e:
        print(f"\n❌ Capture failed: {e}")


async def check_recent_photos():
    """Test recent photos retrieval and display results"""
    if not (recent_tool := mcp._tool_manager._tools.get("get_recent_photos")):
        return

    print("\n3. Testing recent photos retrieval...")
    result = await recent_tool.run(arguments={"limit": 5})
    photos_data = extract_tool_result(result)

    # Handle wrapped result format
    if isinstance(photos_data, dict) and "result" in photos_data:
        photos = photos_data["result"]
    else:
        photos = photos_data if isinstance(photos_data, list) else []

    print(f"   Found {len(photos)} recent photos")
    for i, photo in enumerate(photos, 1):
        print(f"   {i}. Time: {photo['timestamp'][:19]}")


async def check_camera_hardware():
    """
    Diagnostic check for camera hardware and configuration.

    This is a manual verification tool, not an automated test.
    It performs real hardware operations to verify camera setup.
    """
    print("=" * 60)
    print("CAMERA HARDWARE DIAGNOSTIC CHECK")
    print("=" * 60)

    # Reset cycle and enable tools
    reset_cycle()
    current_cycle_status["written"] = True

    # Run diagnostic checks
    await check_status()
    await check_capture()
    await check_recent_photos()

    print("\n" + "=" * 60)
    print("DIAGNOSTIC CHECK COMPLETE")
    print("=" * 60)

    # Cleanup camera resources
    import tools.camera as camera_module
    camera_module.cleanup_camera()

if __name__ == "__main__":
    """
    Entry point for manual camera hardware verification.
    This script is excluded from pytest discovery by design.
    """
    print("Starting camera hardware diagnostic...")
    print("Make sure your USB camera is connected.")
    print(f"Current device index: {os.environ.get('CAMERA_DEVICE_INDEX', '0')}")
    print("If camera not found, try editing CAMERA_DEVICE_INDEX in this file.\n")

    asyncio.run(check_camera_hardware())
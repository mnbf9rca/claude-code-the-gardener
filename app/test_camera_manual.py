#!/usr/bin/env python
"""
Manual test script for camera functionality.
Run this to test if your USB camera works with the configuration.
"""
import asyncio
import json
import os
from pathlib import Path

# Set up test environment
os.environ["CAMERA_ENABLED"] = "true"
os.environ["CAMERA_DEVICE_INDEX"] = "0"  # Try 0, 1, or 2 if camera not found
os.environ["CAMERA_SAVE_PATH"] = "./test_photos"

from server import mcp
from shared_state import reset_cycle, current_cycle_status

async def test_camera():
    """Test camera functionality"""
    print("=" * 60)
    print("CAMERA TEST SCRIPT")
    print("=" * 60)

    # Reset cycle and enable tools
    reset_cycle()
    current_cycle_status["written"] = True

    # Get camera status tool
    status_tool = mcp._tool_manager._tools.get("get_camera_status")
    if status_tool:
        print("\n1. Checking camera status...")
        result = await status_tool.run(arguments={})
        status = json.loads(result.content[0].text)
        print(json.dumps(status, indent=2))

        if not status.get("opencv_available"):
            print("\n⚠️  OpenCV not installed. Install with: pip install opencv-python")
            print("   Camera will run in mock mode.")

        if not status.get("camera_available") and status.get("opencv_available"):
            print("\n⚠️  Camera not detected. Try different CAMERA_DEVICE_INDEX (0, 1, 2...)")
            print("   On Mac: Built-in camera is usually 0")
            print("   On RPi: USB camera usually at /dev/video0 (index 0)")

    # Test capture
    capture_tool = mcp._tool_manager._tools.get("capture")
    if capture_tool:
        print("\n2. Testing photo capture...")
        try:
            result = await capture_tool.run(arguments={})
            photo = json.loads(result.content[0].text)
            print(f"   Mode: {photo['mode']}")
            print(f"   Success: {photo['success']}")
            print(f"   URL/Path: {photo['url']}")

            if photo['mode'] == 'real':
                print(f"\n✅ Real camera capture successful!")
                print(f"   Photo saved to: {photo['url']}")

                # Check if file exists
                if Path(photo['url']).exists():
                    file_size = Path(photo['url']).size() / 1024
                    print(f"   File size: {file_size:.1f} KB")
            else:
                print(f"\n⚠️  Running in mock mode (no real camera available)")

        except Exception as e:
            print(f"\n❌ Capture failed: {e}")

    # Test recent photos
    recent_tool = mcp._tool_manager._tools.get("get_recent_photos")
    if recent_tool:
        print("\n3. Testing recent photos retrieval...")
        result = await recent_tool.run(arguments={"limit": 5})
        if result.content:
            photos = json.loads(result.content[0].text)
            print(f"   Found {len(photos)} recent photos")
            for i, photo in enumerate(photos, 1):
                print(f"   {i}. Mode: {photo['mode']}, Time: {photo['timestamp'][:19]}")

    print("\n" + "=" * 60)
    print("TEST COMPLETE")
    print("=" * 60)

    # Cleanup camera resources
    import tools.camera as camera_module
    camera_module.cleanup_camera()

if __name__ == "__main__":
    print("Starting camera test...")
    print("Make sure your USB camera is connected.")
    print(f"Current device index: {os.environ.get('CAMERA_DEVICE_INDEX', '0')}")
    print("If camera not found, try editing CAMERA_DEVICE_INDEX above.\n")

    asyncio.run(test_camera())
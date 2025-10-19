#!/usr/bin/env python3
"""
Script to capture test photos for use in tests
"""
import os
import sys
from pathlib import Path
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

import cv2
from dotenv import load_dotenv

load_dotenv()

def capture_test_photos():
    """Capture a few test photos for use in tests"""

    # Create test fixtures directory
    fixtures_dir = Path(__file__).parent / "test_fixtures" / "photos"
    fixtures_dir.mkdir(parents=True, exist_ok=True)

    # Try to initialize camera
    camera = cv2.VideoCapture(0)

    if not camera.isOpened():
        print("No camera available on this system")
        return False

    # Set camera properties
    camera.set(cv2.CAP_PROP_FRAME_WIDTH, 1920)
    camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)

    print("Camera initialized successfully")
    print(f"Capturing test photos to {fixtures_dir}")

    # Capture 5 photos with slight delay between them
    for i in range(5):
        # Clear buffer
        for _ in range(3):
            camera.read()

        # Capture frame
        ret, frame = camera.read()
        if not ret or frame is None:
            print(f"Failed to capture photo {i+1}")
            continue

        # Save with descriptive name
        filename = f"test_plant_{i+1:02d}.jpg"
        filepath = fixtures_dir / filename

        cv2.imwrite(str(filepath), frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
        print(f"Captured {filename}")

        # Brief pause between captures
        cv2.waitKey(500)

    # Release camera
    camera.release()
    print("Camera released")

    # List captured files
    photos = list(fixtures_dir.glob("*.jpg"))
    print(f"\nCaptured {len(photos)} test photos:")
    for photo in photos:
        size = photo.stat().st_size / 1024
        print(f"  {photo.name} ({size:.1f} KB)")

    return True

if __name__ == "__main__":
    success = capture_test_photos()
    sys.exit(0 if success else 1)
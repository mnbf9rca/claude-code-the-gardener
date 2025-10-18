"""
Camera Tool - Capture photos of the plant
Supports real USB webcam capture with fallback to mock mode.
Works on both Mac and Raspberry Pi.
"""
import os
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional, Tuple
from pydantic import BaseModel, Field
from fastmcp import FastMCP
from shared_state import current_cycle_status

# Try to import camera dependencies
try:
    import cv2
    OPENCV_AVAILABLE = True
except ImportError:
    OPENCV_AVAILABLE = False
    logging.warning("OpenCV not available, camera will run in mock mode")

try:
    from PIL import Image
    import numpy as np
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    logging.warning("Pillow not available, camera will run in mock mode")

# Load configuration
from dotenv import load_dotenv
load_dotenv()

# Camera configuration with defaults
CAMERA_CONFIG = {
    "enabled": os.getenv("CAMERA_ENABLED", "true").lower() == "true",
    "device_index": int(os.getenv("CAMERA_DEVICE_INDEX", "0")),
    "save_path": Path(os.getenv("CAMERA_SAVE_PATH", "./photos")),
    "image_width": int(os.getenv("CAMERA_IMAGE_WIDTH", "1920")),
    "image_height": int(os.getenv("CAMERA_IMAGE_HEIGHT", "1080")),
    "image_quality": int(os.getenv("CAMERA_IMAGE_QUALITY", "85")),
    "capture_timeout": int(os.getenv("CAMERA_CAPTURE_TIMEOUT", "5")),
}

# Storage for captured photos
photo_history = []

# Initialize camera once if available
camera = None
camera_available = False


class CaptureResponse(BaseModel):
    """Response from capturing a photo"""
    url: str = Field(..., description="URL or path to the captured image")
    timestamp: str = Field(..., description="When the photo was captured")
    mode: str = Field(..., description="Capture mode (real/mock)")
    success: bool = Field(..., description="Whether capture was successful")


def initialize_camera() -> Tuple[bool, Optional[object]]:
    """
    Initialize the camera if available.
    Returns: (success, camera_object)
    """
    if not CAMERA_CONFIG["enabled"]:
        logging.info("Camera disabled via configuration")
        return False, None

    if not OPENCV_AVAILABLE:
        logging.warning("OpenCV not installed, cannot use real camera")
        return False, None

    try:
        # Try to open the camera
        cam = cv2.VideoCapture(CAMERA_CONFIG["device_index"])

        # Set camera properties
        cam.set(cv2.CAP_PROP_FRAME_WIDTH, CAMERA_CONFIG["image_width"])
        cam.set(cv2.CAP_PROP_FRAME_HEIGHT, CAMERA_CONFIG["image_height"])

        # Test if camera is working
        ret, frame = cam.read()
        if ret and frame is not None:
            logging.info(f"Camera initialized successfully on device {CAMERA_CONFIG['device_index']}")
            return True, cam
        else:
            cam.release()
            logging.warning("Camera opened but couldn't read frame")
            return False, None

    except Exception as e:
        logging.error(f"Failed to initialize camera: {e}")
        return False, None


def capture_real_photo() -> Optional[str]:
    """
    Capture a real photo using the USB camera.
    Returns the file path if successful, None otherwise.
    """
    global camera, camera_available

    # Initialize camera on first use
    if camera is None and not camera_available:
        camera_available, camera = initialize_camera()

    if not camera_available or camera is None:
        return None

    try:
        # Ensure save directory exists
        CAMERA_CONFIG["save_path"].mkdir(parents=True, exist_ok=True)

        # Clear buffer by reading a few frames (cameras can have stale frames)
        for _ in range(3):
            camera.read()

        # Capture frame
        ret, frame = camera.read()
        if not ret or frame is None:
            logging.error("Failed to capture frame")
            return None

        # Generate filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]  # milliseconds
        filename = f"plant_{timestamp}.jpg"
        filepath = CAMERA_CONFIG["save_path"] / filename

        # Save image with specified quality
        if PIL_AVAILABLE:
            # Convert BGR to RGB (OpenCV uses BGR, PIL uses RGB)
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            img = Image.fromarray(rgb_frame)
            img.save(filepath, "JPEG", quality=CAMERA_CONFIG["image_quality"])
        else:
            # Fallback to OpenCV save
            cv2.imwrite(
                str(filepath),
                frame,
                [cv2.IMWRITE_JPEG_QUALITY, CAMERA_CONFIG["image_quality"]]
            )

        logging.info(f"Photo captured: {filepath}")
        return str(filepath)

    except Exception as e:
        logging.error(f"Error capturing photo: {e}")
        return None


def capture_mock_photo() -> str:
    """
    Generate a mock photo URL for testing.
    Returns a placeholder URL.
    """
    timestamp = datetime.now().isoformat()
    # Generate a placeholder URL based on timestamp
    filename = timestamp.replace(':', '-').replace('.', '-') + ".jpg"
    return f"http://192.168.1.100/photos/{filename}"


def cleanup_camera():
    """Release camera resources when shutting down."""
    global camera
    if camera is not None:
        camera.release()
        camera = None
        logging.info("Camera released")


def setup_camera_tools(mcp: FastMCP):
    """Set up camera tools on the MCP server"""

    @mcp.tool()
    async def capture() -> CaptureResponse:
        """
        Take a photo of the plant.
        Uses real USB camera if available, otherwise returns mock data.

        Configuration via environment variables:
        - CAMERA_ENABLED: true/false to enable real camera
        - CAMERA_DEVICE_INDEX: 0, 1, 2, etc. for camera selection
        - CAMERA_SAVE_PATH: Directory to save photos
        """
        # Check if plant status has been written first
        if not current_cycle_status["written"]:
            raise ValueError("Must call write_status first before capturing photo")

        timestamp = datetime.now().isoformat()

        # Try to capture real photo
        real_path = capture_real_photo()

        if real_path:
            # Real photo captured successfully
            photo_entry = {
                "url": real_path,
                "timestamp": timestamp,
                "mode": "real"
            }
            photo_history.append(photo_entry)

            # Keep history limited to prevent memory issues
            if len(photo_history) > 100:
                photo_history.pop(0)

            return CaptureResponse(
                url=real_path,
                timestamp=timestamp,
                mode="real",
                success=True
            )
        else:
            # Fallback to mock mode
            mock_url = capture_mock_photo()

            photo_entry = {
                "url": mock_url,
                "timestamp": timestamp,
                "mode": "mock"
            }
            photo_history.append(photo_entry)

            # Keep history limited to prevent memory issues
            if len(photo_history) > 100:
                photo_history.pop(0)

            return CaptureResponse(
                url=mock_url,
                timestamp=timestamp,
                mode="mock",
                success=True
            )

    @mcp.tool()
    async def get_recent_photos(
        limit: int = Field(5, description="Number of recent photos to return", ge=1, le=20)
    ) -> list[dict]:
        """
        Get URLs of recently captured photos.
        Returns list of {url, timestamp, mode} dictionaries.
        """
        return photo_history[-limit:] if photo_history else []

    @mcp.tool()
    async def get_camera_status() -> dict:
        """
        Get current camera configuration and status.
        Useful for debugging camera issues.
        """
        global camera_available

        # Check current camera status
        if camera is None and not camera_available:
            camera_available, _ = initialize_camera()

        return {
            "opencv_available": OPENCV_AVAILABLE,
            "pil_available": PIL_AVAILABLE,
            "camera_enabled": CAMERA_CONFIG["enabled"],
            "camera_available": camera_available,
            "device_index": CAMERA_CONFIG["device_index"],
            "save_path": str(CAMERA_CONFIG["save_path"]),
            "resolution": f"{CAMERA_CONFIG['image_width']}x{CAMERA_CONFIG['image_height']}",
            "image_quality": CAMERA_CONFIG["image_quality"],
            "photos_captured": len(photo_history),
            "mode": "real" if camera_available else "mock"
        }


# Register cleanup on module unload
import atexit
atexit.register(cleanup_camera)
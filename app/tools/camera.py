"""
Camera Tool - Capture photos of the plant
Supports real USB webcam capture.
Works on both Mac and Raspberry Pi.
"""
import os
import logging
import atexit
from pathlib import Path
from datetime import datetime
from typing import Optional, Tuple, Dict, List, Any
from pydantic import BaseModel, Field
from fastmcp import FastMCP
from shared_state import current_cycle_status
from dotenv import load_dotenv

# Required imports - no conditional loading
import cv2
from PIL import Image

# Load configuration
load_dotenv()

# Camera configuration with defaults
CAMERA_CONFIG: Dict[str, Any] = {
    "enabled": os.getenv("CAMERA_ENABLED", "true").lower() == "true",
    "device_index": int(os.getenv("CAMERA_DEVICE_INDEX", "0")),
    "save_path": Path(os.getenv("CAMERA_SAVE_PATH", "./photos")),
    "image_width": int(os.getenv("CAMERA_IMAGE_WIDTH", "1920")),
    "image_height": int(os.getenv("CAMERA_IMAGE_HEIGHT", "1080")),
    "image_quality": int(os.getenv("CAMERA_IMAGE_QUALITY", "85")),
    "capture_timeout": int(os.getenv("CAMERA_CAPTURE_TIMEOUT", "5")),
}

# Camera state
camera: Optional[cv2.VideoCapture] = None
camera_available: bool = False
camera_error: Optional[str] = None


def load_photo_history_from_disk() -> List[Dict[str, str]]:
    """Load existing photos from the save directory to reconstruct history."""
    history = []
    save_path = CAMERA_CONFIG["save_path"]

    if save_path.exists() and save_path.is_dir():
        # Find all jpg files matching our naming pattern
        photo_files = list(save_path.glob("plant_*.jpg"))

        # Sort by modification time (or could parse timestamp from filename)
        photo_files.sort(key=lambda p: p.stat().st_mtime)

        # Take the most recent 100 to match our history limit
        for photo_path in photo_files[-100:]:
            # Extract timestamp from filename if possible
            # Filename format: plant_YYYYMMDD_HHMMSS_mmm.jpg
            try:
                filename = photo_path.stem  # Remove .jpg
                parts = filename.split('_')
                if len(parts) >= 4:
                    date_part = parts[1]  # YYYYMMDD
                    time_part = parts[2]  # HHMMSS
                    ms_part = parts[3] if len(parts) > 3 else "000"

                    # Reconstruct ISO timestamp
                    year = date_part[:4]
                    month = date_part[4:6]
                    day = date_part[6:8]
                    hour = time_part[:2]
                    minute = time_part[2:4]
                    second = time_part[4:6]

                    timestamp = f"{year}-{month}-{day}T{hour}:{minute}:{second}.{ms_part}"
                else:
                    # Fallback to file modification time
                    timestamp = datetime.fromtimestamp(photo_path.stat().st_mtime).isoformat()
            except Exception:
                # If we can't parse the filename, use file modification time
                timestamp = datetime.fromtimestamp(photo_path.stat().st_mtime).isoformat()

            history.append({
                "url": str(photo_path),
                "timestamp": timestamp
            })

    logging.info(f"Loaded {len(history)} photos from disk into history")
    return history


# Storage for captured photos - hydrate from disk on module load
photo_history: List[Dict[str, str]] = load_photo_history_from_disk()


class CaptureResponse(BaseModel):
    """Response from capturing a photo"""
    success: bool = Field(..., description="Whether capture was successful")
    url: Optional[str] = Field(None, description="URL or path to the captured image")
    timestamp: Optional[str] = Field(None, description="When the photo was captured")
    error: Optional[str] = Field(None, description="Error message if capture failed")


def initialize_camera() -> Tuple[bool, Optional[cv2.VideoCapture], Optional[str]]:
    """
    Initialize the camera if available.
    Returns: (success, camera_object, error_message)
    """
    if not CAMERA_CONFIG["enabled"]:
        error_msg = "Camera disabled via configuration"
        logging.info(error_msg)
        return False, None, error_msg

    try:
        # Try to open the camera
        device_index = CAMERA_CONFIG["device_index"]
        cam = cv2.VideoCapture(device_index)

        if not cam.isOpened():
            error_msg = f"Cannot open camera at index {device_index}"
            logging.warning(error_msg)
            return False, None, error_msg

        # Set camera properties
        cam.set(cv2.CAP_PROP_FRAME_WIDTH, CAMERA_CONFIG["image_width"])
        cam.set(cv2.CAP_PROP_FRAME_HEIGHT, CAMERA_CONFIG["image_height"])

        # Test if camera is working
        ret, frame = cam.read()
        if ret and frame is not None:
            logging.info(f"Camera initialized successfully on device {device_index}")
            return True, cam, None
        else:
            cam.release()
            error_msg = f"Camera opened but couldn't read frame from device {device_index}"
            logging.warning(error_msg)
            return False, None, error_msg

    except Exception as e:
        error_msg = f"Failed to initialize camera: {str(e)}"
        logging.error(error_msg)
        return False, None, error_msg


def capture_real_photo() -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Capture a real photo using the USB camera.
    Returns: (success, file_path, error_message)
    """
    global camera, camera_available, camera_error

    # Initialize camera on first use
    if camera is None and not camera_available:
        camera_available, camera, camera_error = initialize_camera()

    if not camera_available or camera is None:
        return False, None, camera_error or "Camera not available"

    try:
        # Ensure save directory exists
        save_path = CAMERA_CONFIG["save_path"]
        save_path.mkdir(parents=True, exist_ok=True)

        # Clear buffer by reading a few frames (cameras can have stale frames)
        for _ in range(3):
            camera.read()

        # Capture frame
        ret, frame = camera.read()
        if not ret or frame is None:
            error_msg = "Failed to capture frame"
            logging.error(error_msg)
            return False, None, error_msg

        # Generate filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]  # milliseconds
        filename = f"plant_{timestamp}.jpg"
        filepath = save_path / filename

        # Save image with specified quality
        # Convert BGR to RGB (OpenCV uses BGR, PIL uses RGB)
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        img = Image.fromarray(rgb_frame)
        img.save(filepath, "JPEG", quality=CAMERA_CONFIG["image_quality"])

        logging.info(f"Photo captured: {filepath}")
        return True, str(filepath), None

    except Exception as e:
        error_msg = f"Error capturing photo: {str(e)}"
        logging.error(error_msg)
        return False, None, error_msg


def cleanup_camera():
    """Release camera resources when shutting down."""
    global camera
    if camera is not None:
        try:
            camera.release()
            camera = None
            logging.info("Camera released")
        except Exception as e:
            logging.error(f"Error releasing camera: {e}")


def setup_camera_tools(mcp: FastMCP):
    """Set up camera tools on the MCP server"""

    @mcp.tool()
    async def capture() -> CaptureResponse:
        """
        Take a photo of the plant.
        Uses real USB camera if available, otherwise returns error.

        Configuration via environment variables:
        - CAMERA_ENABLED: true/false to enable real camera
        - CAMERA_DEVICE_INDEX: 0, 1, 2, etc. for camera selection
        - CAMERA_SAVE_PATH: Directory to save photos
        """
        # Check if plant status has been written first
        if not current_cycle_status["written"]:
            return CaptureResponse(
                success=False,
                error="Must call write_status first before capturing photo"
            )

        timestamp = datetime.now().isoformat()

        # Try to capture real photo
        success, photo_path, error_msg = capture_real_photo()

        if success and photo_path:
            # Real photo captured successfully
            photo_entry = {
                "url": photo_path,
                "timestamp": timestamp,
            }
            photo_history.append(photo_entry)

            # Keep history limited to prevent memory issues
            if len(photo_history) > 100:
                photo_history.pop(0)

            return CaptureResponse(
                success=True,
                url=photo_path,
                timestamp=timestamp
            )
        else:
            # Camera unavailable or capture failed
            return CaptureResponse(
                success=False,
                error=error_msg or "Camera unavailable"
            )

    @mcp.tool()
    async def get_recent_photos(
        limit: int = Field(5, description="Number of recent photos to return", ge=1, le=20)
    ) -> List[Dict[str, str]]:
        """
        Get URLs of recently captured photos.
        Returns list of {url, timestamp} dictionaries.
        """
        # Validate limit is within acceptable range
        if limit < 1:
            limit = 1
        elif limit > 20:
            limit = 20

        return photo_history[-limit:] if photo_history else []

    @mcp.tool()
    async def get_camera_status() -> Dict[str, Any]:
        """
        Get current camera configuration and status.
        Useful for debugging camera issues.
        """
        global camera_available, camera_error

        # Check current camera status if not already checked
        if camera is None and not camera_available:
            camera_available, _, camera_error = initialize_camera()

        return {
            "camera_enabled": CAMERA_CONFIG["enabled"],
            "camera_available": camera_available,
            "device_index": CAMERA_CONFIG["device_index"],
            "save_path": str(CAMERA_CONFIG["save_path"]),
            "resolution": f"{CAMERA_CONFIG['image_width']}x{CAMERA_CONFIG['image_height']}",
            "image_quality": CAMERA_CONFIG["image_quality"],
            "photos_captured": len(photo_history),
            "error": camera_error if not camera_available else None
        }


# Register cleanup on module unload
atexit.register(cleanup_camera)
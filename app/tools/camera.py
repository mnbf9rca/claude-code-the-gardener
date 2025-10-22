"""
Camera Tool - Capture photos of the plant
Supports real USB webcam capture.
Works on both Mac and Raspberry Pi.
"""
import os
import logging
import atexit
import threading
import heapq
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Tuple, Dict, List, Any
from pydantic import BaseModel, Field
from fastmcp import FastMCP
from utils.jsonl_history import JsonlHistory
from utils.paths import get_app_dir
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
    "save_path": get_app_dir("photos"),
    "image_width": int(os.getenv("CAMERA_IMAGE_WIDTH", "1920")),
    "image_height": int(os.getenv("CAMERA_IMAGE_HEIGHT", "1080")),
    "image_quality": int(os.getenv("CAMERA_IMAGE_QUALITY", "85")),
    "capture_timeout": int(os.getenv("CAMERA_CAPTURE_TIMEOUT", "5")),
}

# Server configuration for photo URLs
MCP_PUBLIC_HOST = os.getenv("MCP_PUBLIC_HOST", "localhost")
MCP_PORT = os.getenv("MCP_PORT", "8000")
SERVER_URL = f"http://{MCP_PUBLIC_HOST}:{MCP_PORT}"

# Photo history configuration
PHOTO_HISTORY_LIMIT = 100  # Maximum number of photos to keep in memory

# Camera state
camera: Optional[cv2.VideoCapture] = None
camera_available: bool = False
camera_error: Optional[str] = None

# State persistence - audit log for camera usage
# Used for time-bucketed queries via get_camera_history_bucketed()
usage_history = JsonlHistory(
    file_path=get_app_dir("data") / "camera_usage.jsonl",
    max_memory_entries=1000  # Standard cache size for querying
)


def log_tool_usage(tool_name: str, event_data: Dict[str, Any]) -> None:
    """
    Append a tool usage event to the JSONL usage file.
    Uses append-only pattern via JsonlHistory utility.
    """
    try:
        # Create event with tool name and timestamp
        event = {
            "tool": tool_name,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **event_data
        }

        # Append to history (handles both memory and disk)
        usage_history.append(event)

        logging.debug(f"Logged {tool_name} usage to {usage_history.file_path}")

    except Exception as e:
        # Don't fail the tool call if logging fails
        logging.warning(f"Failed to log tool usage: {e}")


def load_photo_history_from_disk() -> List[Dict[str, str]]:
    """
    Load existing photos from the save directory to reconstruct history.
    Optimized for large directories by limiting files processed.
    """
    history = []
    save_path = CAMERA_CONFIG["save_path"]
    max_photos = PHOTO_HISTORY_LIMIT

    if save_path.exists() and save_path.is_dir():
        # Find all jpg files matching our naming pattern
        photo_files = save_path.glob("plant_*.jpg")

        # Use heapq.nlargest to efficiently get the N most recent files
        # without sorting all files (O(n log k) vs O(n log n))
        recent_files = heapq.nlargest(
            max_photos,
            photo_files,
            key=lambda p: p.stat().st_mtime
        )

        # Sort the selected files by modification time (oldest to newest)
        recent_files.sort(key=lambda p: p.stat().st_mtime)

        # Process files to extract timestamps
        for photo_path in recent_files:
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
    url: str = Field(..., description="URL to the captured image")
    timestamp: str = Field(..., description="When the photo was captured (ISO 8601 UTC)")


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


def _read_camera_frame(camera, result_container: Dict[str, Any]):
    """
    Helper function to read camera frame in a separate thread.
    Stores result in result_container dict.
    """
    try:
        ret, frame = camera.read()
        result_container['ret'] = ret
        result_container['frame'] = frame
    except Exception as e:
        result_container['error'] = str(e)


def capture_real_photo() -> Tuple[str, str]:
    """
    Capture a real photo using the USB camera with timeout protection.
    Returns: (file_path, timestamp_iso)
    Raises: ValueError if camera is unavailable or capture fails
    """
    global camera, camera_available, camera_error

    # Initialize camera on first use
    if camera is None and not camera_available:
        camera_available, camera, camera_error = initialize_camera()

    if not camera_available or camera is None:
        raise ValueError(camera_error or "Camera not available")

    try:
        # Ensure save directory exists
        save_path = CAMERA_CONFIG["save_path"]
        save_path.mkdir(parents=True, exist_ok=True)

        # Clear buffer by reading a few frames (cameras can have stale frames)
        for _ in range(3):
            camera.read()

        # Capture frame with timeout protection
        timeout_seconds = CAMERA_CONFIG["capture_timeout"]
        result_container: Dict[str, Any] = {}
        read_thread = threading.Thread(target=_read_camera_frame, args=(camera, result_container))
        read_thread.daemon = True
        read_thread.start()
        read_thread.join(timeout_seconds)

        if read_thread.is_alive():
            error_msg = f"Camera read timed out after {timeout_seconds} seconds"
            logging.error(error_msg)
            raise ValueError(error_msg)

        if 'error' in result_container:
            error_msg = f"Camera read error: {result_container['error']}"
            logging.error(error_msg)
            raise ValueError(error_msg)

        ret = result_container.get('ret', False)
        frame = result_container.get('frame')

        if not ret or frame is None:
            error_msg = "Failed to capture frame"
            logging.error(error_msg)
            raise ValueError(error_msg)

        # Generate timestamp once for both filename and response (ensures consistency)
        now = datetime.now(timezone.utc)
        timestamp_iso = now.isoformat()
        timestamp_filename = now.strftime("%Y%m%d_%H%M%S_%f")[:-3]  # milliseconds for filename

        filename = f"plant_{timestamp_filename}.jpg"
        filepath = save_path / filename

        # Save image with specified quality
        # Convert BGR to RGB (OpenCV uses BGR, PIL uses RGB)
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        img = Image.fromarray(rgb_frame)
        img.save(filepath, "JPEG", quality=CAMERA_CONFIG["image_quality"])

        logging.info(f"Photo captured: {filepath}")
        return str(filepath), timestamp_iso

    except Exception as e:
        error_msg = f"Error capturing photo: {str(e)}"
        logging.error(error_msg)
        raise ValueError(error_msg)


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
    async def capture_photo() -> CaptureResponse:
        """
        Take a photo of the plant.
        Uses real USB camera if available, otherwise raises an error.
        Note that you may need to use CURL to fetch the actual images as they are not accessible from the internet.

        Configuration via environment variables:
        - CAMERA_ENABLED: true/false to enable real camera
        - CAMERA_DEVICE_INDEX: 0, 1, 2, etc. for camera selection
        - CAMERA_SAVE_PATH: Directory to save photos. Note this path is not accessible to you and is for debugging purposes only.

        Raises:
            ValueError: If camera is unavailable or capture fails
        """
        # Try to capture real photo (timestamp generated inside for consistency)
        # Raises ValueError on failure
        try:
            photo_path, timestamp = capture_real_photo()
        except ValueError as e:
            # Camera unavailable or capture failed
            # Log failed capture
            log_tool_usage("capture", {
                "success": False,
                "error": str(e)
            })
            # Re-raise to signal failure to MCP server
            raise

        # Real photo captured successfully
        # Convert file path to HTTP URL
        filename = Path(photo_path).name
        photo_url = f"{SERVER_URL}/photos/{filename}"

        photo_entry = {
            "url": photo_url,
            "timestamp": timestamp,
        }
        photo_history.append(photo_entry)

        # Keep history limited to prevent memory issues
        if len(photo_history) > PHOTO_HISTORY_LIMIT:
            photo_history.pop(0)

        # Log successful capture
        log_tool_usage("capture", {
            "success": True,
            "photo_path": photo_path,
            "photo_url": photo_url
        })

        return CaptureResponse(
            url=photo_url,
            timestamp=timestamp
        )

    @mcp.tool()
    async def get_recent_photos(
        limit: int = Field(5, description="Number of recent photos to return", ge=1, le=20)
    ) -> List[Dict[str, str]]:
        """
        Get URLs of recently captured photos.
        Returns list of {url, timestamp} dictionaries.
        Note that you may need to use CURL to fetch the actual images as they are not accessible from the internet.
        """
        # Validate limit is within acceptable range
        if limit < 1:
            limit = 1
        elif limit > 20:
            limit = 20

        result = photo_history[-limit:] if photo_history else []

        # Log tool usage
        log_tool_usage("get_recent_photos", {
            "limit": limit,
            "photos_returned": len(result)
        })

        return result

    @mcp.tool()
    async def get_camera_status() -> Dict[str, Any]:
        """
        Get current camera configuration and status.
        Useful for debugging camera issues.
        """
        global camera, camera_available, camera_error

        # Check current camera status if not already checked
        if camera is None and not camera_available:
            camera_available, camera, camera_error = initialize_camera()

        status = {
            "camera_enabled": CAMERA_CONFIG["enabled"],
            "camera_available": camera_available,
            "device_index": CAMERA_CONFIG["device_index"],
            "save_path": str(CAMERA_CONFIG["save_path"]),
            "resolution": f"{CAMERA_CONFIG['image_width']}x{CAMERA_CONFIG['image_height']}",
            "image_quality": CAMERA_CONFIG["image_quality"],
            "photos_captured": len(photo_history),
            "error": None if camera_available else camera_error
        }

        # Log tool usage
        log_tool_usage("get_camera_status", {
            "camera_available": camera_available,
            "photos_captured": len(photo_history)
        })

        return status

    @mcp.tool()
    async def get_camera_history_bucketed(
        hours: int = Field(24, description="Time window in hours (how far back to query)", ge=1),
        samples_per_hour: float = Field(6, description="Bucket density (6 = every 10min, 1 = hourly, 0.042 = daily)", gt=0),
        aggregation: str = Field("middle", description="Strategy: first|last|middle (sampling) or count|sum|mean (aggregation)"),
        value_field: Optional[str] = Field(None, description="Field to aggregate (required for sum/mean)"),
        end_time: Optional[str] = Field(None, description="End of time window (ISO8601 UTC). Defaults to now.")
    ) -> list[dict]:
        """
        Get time-bucketed camera usage history for temporal analysis.

        Queries the usage_history (JSONL audit log) to analyze photo capture patterns.

        Supports two query modes:
        1. Sampling (first/last/middle): Returns sample capture events from each bucket
        2. Aggregation (count/sum/mean): Returns computed statistics per bucket

        Examples:
            - Photo capture rate per hour (last 24h):
              hours=24, samples_per_hour=1, aggregation="count"
            - Photos per day (last month):
              hours=720, samples_per_hour=0.042, aggregation="count"
            - Sample capture events every 10 minutes (last 24h):
              hours=24, samples_per_hour=6, aggregation="middle"

        Returns:
            For sampling: List of usage event dicts with full context
            For aggregation: List of {"bucket_start": str, "bucket_end": str, "value": number, "count": int}
        """
        # Parse end_time if provided
        end_dt = None
        if end_time:
            try:
                end_dt = datetime.fromisoformat(end_time)
            except ValueError as e:
                raise ValueError(
                    f"Invalid end_time format. Expected ISO8601 like '2025-01-15T12:00:00Z'. Error: {str(e)}"
                )

        # Call time-bucketed sample on usage_history (JSONL audit log)
        return usage_history.get_time_bucketed_sample(
            hours=hours,
            samples_per_hour=samples_per_hour,
            timestamp_key="timestamp",
            aggregation=aggregation,
            end_time=end_dt,
            value_field=value_field
        )


# Register cleanup on module unload
atexit.register(cleanup_camera)
"""
Camera Tool - Capture photos of the plant
Mock implementation for now, will integrate with USB webcam later.
"""
from datetime import datetime
from pydantic import BaseModel, Field
from fastmcp import FastMCP
from shared_state import current_cycle_status

# Storage for captured photos
photo_history = []


class CaptureResponse(BaseModel):
    """Response from capturing a photo"""
    url: str = Field(..., description="URL or path to the captured image")
    timestamp: str = Field(..., description="When the photo was captured")


def setup_camera_tools(mcp: FastMCP):
    """Set up camera tools on the MCP server"""

    @mcp.tool()
    async def capture() -> CaptureResponse:
        """
        Take a photo of the plant.
        Returns a placeholder URL for now.
        In production, this will capture from the USB webcam.
        """
        # Check if plant status has been written first
        if not current_cycle_status["written"]:
            raise ValueError("Must call write_status first before capturing photo")

        timestamp = datetime.now().isoformat()

        # Generate a placeholder URL based on timestamp
        # In production, this would save the actual image and return the path
        url = f"http://192.168.1.100/photos/{timestamp.replace(':', '-').replace('.', '-')}.jpg"

        # Store in history
        photo_entry = {
            "url": url,
            "timestamp": timestamp
        }
        photo_history.append(photo_entry)

        # Keep history limited to prevent memory issues
        if len(photo_history) > 100:
            photo_history.pop(0)

        return CaptureResponse(
            url=url,
            timestamp=timestamp
        )

    @mcp.tool()
    async def get_recent_photos(
        limit: int = Field(5, description="Number of recent photos to return", ge=1, le=20)
    ) -> list[dict]:
        """
        Get URLs of recently captured photos.
        Returns list of {url, timestamp} dictionaries.
        """
        return photo_history[-limit:] if photo_history else []
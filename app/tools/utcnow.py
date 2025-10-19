"""UTC time query tool for the plant care system.

Provides the current UTC time to Claude so it can understand temporal context
without needing to infer from other tool responses.
"""

from datetime import datetime, timezone
from pydantic import BaseModel, Field
from fastmcp import FastMCP


class TimeResponse(BaseModel):
    """Current UTC time response"""
    timestamp: str = Field(..., description="Current UTC time in ISO8601 format")


def setup_utcnow_tools(mcp: FastMCP):
    """Set up UTC time query tools on the MCP server"""

    @mcp.tool()
    async def get_current_time() -> TimeResponse:
        """
        Get the current UTC time.
        Use this to understand the current date and time for temporal reasoning.
        """
        return TimeResponse(
            timestamp=datetime.now(timezone.utc).isoformat()
        )

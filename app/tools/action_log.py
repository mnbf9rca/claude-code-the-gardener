"""
Action Log Tool - Record all actions taken by Claude
Stores action history for review and analysis.
"""
from typing import Dict, Any, List, Literal
from datetime import datetime, timezone
from pydantic import BaseModel, Field
from fastmcp import FastMCP
from pathlib import Path
from utils.jsonl_history import JsonlHistory

# Constants
DEFAULT_RECENT_LIMIT = 5  # Default number of recent entries
MAX_RECENT_LIMIT = 50  # Maximum entries that can be requested
DEFAULT_SEARCH_HOURS = 24  # Default search window in hours
MAX_MEMORY_ENTRIES = 1000  # Maximum entries to keep in memory

# Valid action types
ActionType = Literal["water", "light", "observe", "alert"]

# State persistence (JSONL format for append-only writes)
STATE_FILE = Path(__file__).parent.parent / "data" / "action_log.jsonl"

# History manager
action_history = JsonlHistory(file_path=STATE_FILE, max_memory_entries=MAX_MEMORY_ENTRIES)


class ActionResponse(BaseModel):
    """Response from logging an action"""
    timestamp: str = Field(..., description="When action was recorded")
    success: bool = Field(..., description="Whether action was logged successfully")


class ActionEntry(BaseModel):
    """A complete action entry"""
    timestamp: str
    type: str
    details: Dict[str, Any]


class RecentActionsResponse(BaseModel):
    """Response from getting recent actions"""
    count: int = Field(..., description="Number of actions returned")
    actions: List[ActionEntry] = Field(..., description="List of action entries")


class SearchResponse(BaseModel):
    """Response from searching actions"""
    count: int = Field(..., description="Number of matching actions")
    actions: List[ActionEntry] = Field(..., description="Matching action entries")


def setup_action_log_tools(mcp: FastMCP):
    """Set up action log tools on the MCP server"""

    @mcp.tool()
    async def log_action(
        type: ActionType = Field(..., description="Type of action: water, light, observe, or alert"),
        details: Dict[str, Any] = Field(..., description="Details about the action taken (flexible JSON)")
    ) -> ActionResponse:
        """
        Log an action taken by Claude.
        This creates a record of all actions for review and analysis.
        """
        # Create action entry
        timestamp = datetime.now(timezone.utc).isoformat()
        action = {
            "timestamp": timestamp,
            "type": type,
            "details": details
        }

        # Append to history (handles both memory and disk)
        action_history.append(action)

        return ActionResponse(
            timestamp=timestamp,
            success=True
        )

    @mcp.tool()
    async def get_recent(
        n: int = Field(default=DEFAULT_RECENT_LIMIT, description=f"Number of recent actions (max {MAX_RECENT_LIMIT})", ge=1, le=MAX_RECENT_LIMIT),
        offset: int = Field(default=0, description="Number of entries to skip from the end (for pagination)", ge=0)
    ) -> RecentActionsResponse:
        """
        Get the N most recent actions with optional pagination.
        offset=0 gets the most recent entries, offset=10 skips the 10 most recent.
        Useful for reviewing recent actions.
        """
        # Get entries with pagination
        recent = action_history.get_recent(n=n, offset=offset)

        # Convert to Pydantic models
        action_entries = [ActionEntry(**a) for a in recent]

        return RecentActionsResponse(
            count=len(action_entries),
            actions=action_entries
        )

    @mcp.tool()
    async def search(
        keyword: str = Field(..., description="Keyword to search for"),
        hours: int = Field(default=DEFAULT_SEARCH_HOURS, description="How many hours back to search", ge=1)
    ) -> SearchResponse:
        """
        Search for actions containing a keyword in the last N hours.
        Searches in action details (converted to string).
        """
        # Get recent actions within the time window
        recent_actions = action_history.get_by_time_window(hours=hours)

        # Filter recent actions for keyword matches
        recent_matching = [
            action for action in recent_actions
            if keyword.lower() in str(action).lower()
        ]

        # Convert to Pydantic models
        action_entries = [ActionEntry(**a) for a in recent_matching]

        return SearchResponse(
            count=len(action_entries),
            actions=action_entries
        )

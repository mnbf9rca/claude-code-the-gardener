"""
Action Log Tool - Record all actions taken by Claude
Stores action history for review and analysis.
"""
from typing import Dict, Any, List, Literal, Optional
from datetime import datetime, timezone
from pydantic import BaseModel, Field
from fastmcp import FastMCP
from utils.jsonl_history import JsonlHistory
from utils.paths import get_app_dir

# Constants
DEFAULT_RECENT_LIMIT = 5  # Default number of recent entries
MAX_RECENT_LIMIT = 50  # Maximum entries that can be requested
DEFAULT_SEARCH_HOURS = 24  # Default search window in hours
MAX_MEMORY_ENTRIES = 1000  # Maximum entries to keep in memory

# Valid action types
ActionType = Literal["water", "light", "observe", "alert"]

# State persistence (JSONL format for append-only writes)
STATE_FILE = get_app_dir("data") / "action_log.jsonl"

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
    async def get_recent_actions(
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
    async def search_actions(
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

    @mcp.tool()
    async def get_action_history_bucketed(
        hours: int = Field(24, description="Time window in hours (how far back to query)", ge=1),
        samples_per_hour: float = Field(6, description="Bucket density (6 = every 10min, 1 = hourly, 0.042 = daily)", gt=0),
        aggregation: str = Field("middle", description="Strategy: first|last|middle (sampling) or count|sum|mean (aggregation)"),
        value_field: Optional[str] = Field(None, description="Field to aggregate (required for sum/mean)"),
        end_time: Optional[str] = Field(None, description="End of time window (ISO8601 UTC). Defaults to now.")
    ) -> list[dict]:
        """
        Get time-bucketed action log history for temporal analysis.

        Supports two query modes:
        1. Sampling (first/last/middle): Returns sample actions from each bucket
        2. Aggregation (count/sum/mean): Returns computed statistics per bucket

        Examples:
            - Count of actions per day (last month):
              hours=720, samples_per_hour=0.042, aggregation="count"
            - Count of actions per hour (last week):
              hours=168, samples_per_hour=1, aggregation="count"
            - Sample actions every 10 minutes (last 24h):
              hours=24, samples_per_hour=6, aggregation="middle"

        Returns:
            For sampling: List of action dicts with full context
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

        # Call time-bucketed sample with appropriate parameters
        return action_history.get_time_bucketed_sample(
            hours=hours,
            samples_per_hour=samples_per_hour,
            timestamp_key="timestamp",
            aggregation=aggregation,
            end_time=end_dt,
            value_field=value_field
        )

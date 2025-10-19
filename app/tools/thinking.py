"""
Thinking Tool - Log Claude's reasoning process
Stores structured thoughts for review and learning.
"""
from typing import Dict, Any, List, Optional
from datetime import datetime
from pydantic import BaseModel, Field
from fastmcp import FastMCP
from pathlib import Path
from utils.jsonl_history import JsonlHistory

# Constants
DEFAULT_RECENT_LIMIT = 3  # Default number of recent entries
MAX_RECENT_LIMIT = 50  # Maximum entries that can be requested
DEFAULT_SEARCH_HOURS = 24  # Default search window in hours
MAX_MEMORY_ENTRIES = 1000  # Maximum entries to keep in memory

# State persistence (JSONL format for append-only writes)
STATE_FILE = Path(__file__).parent.parent / "data" / "thinking.jsonl"

# History manager
thought_history = JsonlHistory(file_path=STATE_FILE, max_memory_entries=MAX_MEMORY_ENTRIES)


class CandidateAction(BaseModel):
    """A candidate action in the thought process"""
    order: int = Field(..., description="Priority order of this action")
    action: str = Field(..., description="Action type (water, light, observe, etc.)")
    value: Optional[int] = Field(None, description="Action value (ml, minutes, etc.)")


class ThoughtInput(BaseModel):
    """Input for logging a thought"""
    observation: str = Field(..., description="What was observed")
    hypothesis: str = Field(..., description="Hypothesis about what's happening")
    candidate_actions: List[CandidateAction] = Field(..., description="Possible actions to take")
    reasoning: str = Field(..., description="Why this hypothesis and these actions")
    uncertainties: str = Field(..., description="What's uncertain or needs monitoring")
    tags: List[str] = Field(default_factory=list, description="Tags for categorization")


class ThoughtResponse(BaseModel):
    """Response from logging a thought"""
    timestamp: str = Field(..., description="When thought was recorded")
    success: bool = Field(..., description="Whether thought was logged successfully")


class ThoughtEntry(BaseModel):
    """A complete thought entry with all fields"""
    timestamp: str
    observation: str
    hypothesis: str
    candidate_actions: List[Dict[str, Any]]
    reasoning: str
    uncertainties: str
    tags: List[str]


class RecentThoughtsResponse(BaseModel):
    """Response from getting recent thoughts"""
    count: int = Field(..., description="Number of thoughts returned")
    thoughts: List[ThoughtEntry] = Field(..., description="List of thought entries")


class SearchResponse(BaseModel):
    """Response from searching thoughts"""
    count: int = Field(..., description="Number of matching thoughts")
    thoughts: List[ThoughtEntry] = Field(..., description="Matching thought entries")


def setup_thinking_tools(mcp: FastMCP):
    """Set up thinking tools on the MCP server"""

    @mcp.tool()
    async def log_thought(
        observation: str = Field(..., description="What was observed about the plant"),
        hypothesis: str = Field(..., description="Your hypothesis about what's happening"),
        candidate_actions: List[Dict[str, Any]] = Field(..., description="List of candidate actions"),
        reasoning: str = Field(..., description="Your reasoning for this hypothesis"),
        uncertainties: str = Field(..., description="What you're uncertain about"),
        tags: List[str] = Field(default_factory=list, description="Tags for categorization")
    ) -> ThoughtResponse:
        """
        Log a structured thought about the plant's state and potential actions.
        This helps build a history of reasoning for review and learning.
        """
        # Create thought entry
        timestamp = datetime.now().isoformat()
        thought = {
            "timestamp": timestamp,
            "observation": observation,
            "hypothesis": hypothesis,
            "candidate_actions": candidate_actions,
            "reasoning": reasoning,
            "uncertainties": uncertainties,
            "tags": tags
        }

        # Append to history (handles both memory and disk)
        thought_history.append(thought)

        return ThoughtResponse(
            timestamp=timestamp,
            success=True
        )

    @mcp.tool()
    async def get_recent(
        n: int = Field(default=DEFAULT_RECENT_LIMIT, description=f"Number of recent thoughts (max {MAX_RECENT_LIMIT})", ge=1, le=MAX_RECENT_LIMIT),
        offset: int = Field(default=0, description="Number of entries to skip from the end (for pagination)", ge=0)
    ) -> RecentThoughtsResponse:
        """
        Get the N most recent thoughts with optional pagination.
        offset=0 gets the most recent entries, offset=10 skips the 10 most recent.
        Useful for reviewing recent reasoning before making decisions.
        """
        # Get entries with pagination
        recent = thought_history.get_recent(n=n, offset=offset)

        # Convert to Pydantic models
        thought_entries = [ThoughtEntry(**t) for t in recent]

        return RecentThoughtsResponse(
            count=len(thought_entries),
            thoughts=thought_entries
        )

    @mcp.tool()
    async def get_range(
        start_time: str = Field(..., description="Start time (ISO8601 format)"),
        end_time: str = Field(..., description="End time (ISO8601 format)")
    ) -> RecentThoughtsResponse:
        """
        Get thoughts within a specific time range.
        Useful for analyzing reasoning during a specific period.
        """
        # Parse time bounds with error handling
        try:
            start_dt = datetime.fromisoformat(start_time)
            end_dt = datetime.fromisoformat(end_time)
        except ValueError as e:
            raise ValueError(
                f"Invalid ISO8601 timestamp format. "
                f"Expected format: 'YYYY-MM-DDTHH:MM:SS' or 'YYYY-MM-DD HH:MM:SS'. "
                f"Error: {str(e)}"
            )

        # Get entries by time range
        matching = thought_history.get_by_time_range(start_dt, end_dt)

        # Convert to Pydantic models
        thought_entries = [ThoughtEntry(**t) for t in matching]

        return RecentThoughtsResponse(
            count=len(thought_entries),
            thoughts=thought_entries
        )

    @mcp.tool()
    async def search(
        keyword: str = Field(..., description="Keyword to search for"),
        hours: int = Field(default=DEFAULT_SEARCH_HOURS, description="How many hours back to search", ge=1)
    ) -> SearchResponse:
        """
        Search for thoughts containing a keyword in the last N hours.
        Searches observation, hypothesis, and reasoning fields.
        """
        # Get entries from time window
        recent_thoughts = thought_history.get_by_time_window(hours=hours)

        # Search within those entries
        keyword_lower = keyword.lower()
        matching = []

        for thought in recent_thoughts:
            # Search in observation, hypothesis, and reasoning fields
            searchable = f"{thought['observation']} {thought['hypothesis']} {thought['reasoning']}".lower()
            if keyword_lower in searchable:
                matching.append(thought)

        # Convert to Pydantic models
        thought_entries = [ThoughtEntry(**t) for t in matching]

        return SearchResponse(
            count=len(thought_entries),
            thoughts=thought_entries
        )

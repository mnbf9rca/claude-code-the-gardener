"""
Action Log Tool - Record all actions taken by Claude
Stores action history for review and analysis.
"""
from typing import Dict, Any, List, Literal
from datetime import datetime, timedelta
from pydantic import BaseModel, Field
from fastmcp import FastMCP
import json
from pathlib import Path
from collections import deque

# Constants
DEFAULT_RECENT_LIMIT = 5  # Default number of recent entries
MAX_RECENT_LIMIT = 50  # Maximum entries that can be requested
DEFAULT_SEARCH_HOURS = 24  # Default search window in hours
MAX_MEMORY_ENTRIES = 1000  # Maximum entries to keep in memory

# Valid action types
ActionType = Literal["water", "light", "observe", "alert"]

# State persistence (JSONL format for append-only writes)
STATE_FILE = Path(__file__).parent.parent / "data" / "action_log.jsonl"

# Storage for action entries (using deque for efficient in-memory operations)
# This only holds recent events in memory; disk file keeps full history forever
action_history: deque = deque()  # Deque of action dictionaries

# State loading flag
_state_loaded = False


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


# State Persistence Functions (JSONL - append-only)
def initialize_state_file():
    """
    Ensure state file exists.
    JSONL files can start empty - each line is a separate JSON event.
    """
    if not STATE_FILE.exists():
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        STATE_FILE.touch()  # Create empty file
        print("Initialized action log file (JSONL)")


def append_event_to_disk(event: Dict[str, Any]):
    """
    Append a single event to the JSONL file (append-only, never deletes history).
    Each line is a complete JSON object representing one action.
    """
    try:
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)

        # Append new event as a single line of JSON
        with open(STATE_FILE, 'a') as f:
            f.write(json.dumps(event) + '\n')
    except Exception as e:
        print(f"Warning: Failed to append event to history: {e}")


def load_state():
    """
    Load action history from JSONL file into memory.
    Loads up to MAX_MEMORY_ENTRIES most recent events.
    Full history remains in file forever for long-term analysis.
    """
    global action_history
    try:
        initialize_state_file()

        if not STATE_FILE.exists() or STATE_FILE.stat().st_size == 0:
            action_history = deque()
            print("No existing action history found")
            return

        # Read JSONL file and load recent events
        all_events = []
        with open(STATE_FILE, 'r') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue

                try:
                    event = json.loads(line)
                    all_events.append(event)
                except (json.JSONDecodeError, KeyError, ValueError) as e:
                    print(f"Warning: Skipping malformed line in history: {e}")
                    continue

        # Keep only the most recent MAX_MEMORY_ENTRIES
        if len(all_events) > MAX_MEMORY_ENTRIES:
            all_events = all_events[-MAX_MEMORY_ENTRIES:]

        action_history = deque(all_events)
        print(f"Loaded {len(action_history)} actions from disk")

    except Exception as e:
        print(f"Error: Failed to load action log: {e}")
        # Return safe defaults if loading fails
        action_history = deque()


def ensure_state_loaded():
    """
    Ensure state has been loaded from disk on first tool invocation.
    This is called by each tool before accessing action_history.
    """
    global _state_loaded

    if not _state_loaded:
        _state_loaded = True
        load_state()


def prune_action_history():
    """
    Keep memory bounded to MAX_MEMORY_ENTRIES.
    Removes oldest entries when limit is exceeded.
    """
    while len(action_history) > MAX_MEMORY_ENTRIES:
        action_history.popleft()


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
        # Ensure state has been loaded from disk
        ensure_state_loaded()

        # Create action entry
        timestamp = datetime.now().isoformat()
        action = {
            "timestamp": timestamp,
            "type": type,
            "details": details
        }

        # Add to in-memory history
        action_history.append(action)

        # Prune if needed to keep memory bounded
        prune_action_history()

        # Append to disk (keeps full history forever)
        append_event_to_disk(action)

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
        # Ensure state has been loaded from disk
        ensure_state_loaded()

        # Get entries with pagination
        # Convert to list for slicing
        all_actions = list(action_history)
        total = len(all_actions)

        # Calculate slice indices
        # offset from the end: -offset-n to -offset (or end if offset is 0)
        if offset == 0:
            # Most recent N entries
            recent = all_actions[-n:] if total >= n else all_actions
        else:
            # Skip offset from the end, then take N
            start_idx = max(0, total - offset - n)
            end_idx = total - offset
            recent = all_actions[start_idx:end_idx]

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
        # Ensure state has been loaded from disk
        ensure_state_loaded()

        # Calculate cutoff time
        cutoff_time = datetime.now() - timedelta(hours=hours)

        # Search for keyword (case-insensitive substring match)
        keyword_lower = keyword.lower()
        matching = []

        for action in action_history:
            action_time = datetime.fromisoformat(action["timestamp"])
            if action_time < cutoff_time:
                continue

            # Search in details (convert to JSON string for searching)
            searchable = json.dumps(action["details"]).lower()
            if keyword_lower in searchable:
                matching.append(action)

        # Convert to Pydantic models
        action_entries = [ActionEntry(**a) for a in matching]

        return SearchResponse(
            count=len(action_entries),
            actions=action_entries
        )

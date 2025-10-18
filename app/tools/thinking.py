"""
Thinking Tool - Log Claude's reasoning process
Stores structured thoughts for review and learning.
"""
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from pydantic import BaseModel, Field
from fastmcp import FastMCP
import json
from pathlib import Path
from collections import deque

# Constants
DEFAULT_RECENT_LIMIT = 3  # Default number of recent entries
MAX_RECENT_LIMIT = 50  # Maximum entries that can be requested
DEFAULT_SEARCH_HOURS = 24  # Default search window in hours
MAX_MEMORY_ENTRIES = 1000  # Maximum entries to keep in memory

# State persistence (JSONL format for append-only writes)
STATE_FILE = Path(__file__).parent.parent / "data" / "thinking.jsonl"

# Storage for thought entries (using deque for efficient in-memory operations)
# This only holds recent events in memory; disk file keeps full history forever
thought_history: deque = deque()  # Deque of thought dictionaries

# State loading flag
_state_loaded = False


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


# State Persistence Functions (JSONL - append-only)
def initialize_state_file():
    """
    Ensure state file exists.
    JSONL files can start empty - each line is a separate JSON event.
    """
    if not STATE_FILE.exists():
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        STATE_FILE.touch()  # Create empty file
        print("Initialized thinking history file (JSONL)")


def append_event_to_disk(event: Dict[str, Any]):
    """
    Append a single event to the JSONL file (append-only, never deletes history).
    Each line is a complete JSON object representing one thought.
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
    Load thought history from JSONL file into memory.
    Loads up to MAX_MEMORY_ENTRIES most recent events.
    Full history remains in file forever for long-term analysis.
    """
    global thought_history
    try:
        initialize_state_file()

        if not STATE_FILE.exists() or STATE_FILE.stat().st_size == 0:
            thought_history = deque()
            print("No existing thought history found")
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

        thought_history = deque(all_events)
        print(f"Loaded {len(thought_history)} thoughts from disk")

    except Exception as e:
        print(f"Error: Failed to load thinking history: {e}")
        # Return safe defaults if loading fails
        thought_history = deque()


def ensure_state_loaded():
    """
    Ensure state has been loaded from disk on first tool invocation.
    This is called by each tool before accessing thought_history.
    """
    global _state_loaded

    if not _state_loaded:
        _state_loaded = True
        load_state()


def prune_thought_history():
    """
    Keep memory bounded to MAX_MEMORY_ENTRIES.
    Removes oldest entries when limit is exceeded.
    """
    while len(thought_history) > MAX_MEMORY_ENTRIES:
        thought_history.popleft()


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
        # Ensure state has been loaded from disk
        ensure_state_loaded()

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

        # Add to in-memory history
        thought_history.append(thought)

        # Prune if needed to keep memory bounded
        prune_thought_history()

        # Append to disk (keeps full history forever)
        append_event_to_disk(thought)

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
        # Ensure state has been loaded from disk
        ensure_state_loaded()

        # Get entries with pagination
        # Convert to list for slicing
        all_thoughts = list(thought_history)
        total = len(all_thoughts)

        # Calculate slice indices
        # offset from the end: -offset-n to -offset (or end if offset is 0)
        if offset == 0:
            # Most recent N entries
            recent = all_thoughts[-n:] if total >= n else all_thoughts
        else:
            # Skip offset from the end, then take N
            start_idx = max(0, total - offset - n)
            end_idx = total - offset
            recent = all_thoughts[start_idx:end_idx]

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
        # Ensure state has been loaded from disk
        ensure_state_loaded()

        # Parse time bounds
        start_dt = datetime.fromisoformat(start_time)
        end_dt = datetime.fromisoformat(end_time)

        # Filter by time range
        matching = []
        for thought in thought_history:
            thought_time = datetime.fromisoformat(thought["timestamp"])
            if start_dt <= thought_time <= end_dt:
                matching.append(thought)

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
        # Ensure state has been loaded from disk
        ensure_state_loaded()

        # Calculate cutoff time
        cutoff_time = datetime.now() - timedelta(hours=hours)

        # Search for keyword (case-insensitive substring match)
        keyword_lower = keyword.lower()
        matching = []

        for thought in thought_history:
            thought_time = datetime.fromisoformat(thought["timestamp"])
            if thought_time < cutoff_time:
                continue

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

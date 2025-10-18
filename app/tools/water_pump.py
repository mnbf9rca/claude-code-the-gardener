"""
Water Pump Tool - Dispense water with daily usage limits
Mock implementation for now, will integrate with ESP32 pump later.
"""
from typing import Dict, Any
from datetime import datetime, timedelta
from pydantic import BaseModel, Field, field_validator
from fastmcp import FastMCP
from shared_state import current_cycle_status
import json
from pathlib import Path
from collections import deque

# Constants
MAX_ML_PER_24H = 500  # Maximum water allowed in 24 hours
MIN_ML_PER_DISPENSE = 10  # Minimum amount per dispense
MAX_ML_PER_DISPENSE = 100  # Maximum amount per dispense

# State persistence (JSONL format for append-only writes)
STATE_FILE = Path(__file__).parent.parent / "data" / "water_pump_history.jsonl"

# Storage for water dispensing history (using deque for efficient in-memory operations)
# This only holds recent events in memory; disk file keeps full history forever
water_history = deque()  # Deque of {timestamp, ml} dictionaries

# State loading flag
_state_loaded = False


class WaterDispenseResponse(BaseModel):
    """Response from dispensing water"""
    dispensed: int = Field(..., description="Amount actually dispensed (ml)")
    remaining_24h: int = Field(..., description="Amount remaining in 24h limit (ml)")
    timestamp: str = Field(..., description="When water was dispensed")


class WaterUsageResponse(BaseModel):
    """Response from checking water usage"""
    used_ml: int = Field(..., description="Total ml used in last 24 hours")
    remaining_ml: int = Field(..., description="ml remaining in 24h limit")
    events: int = Field(..., description="Number of watering events in last 24h")


# State Persistence Functions (JSONL - append-only)
def initialize_state_file():
    """
    Ensure state file exists.
    JSONL files can start empty - each line is a separate JSON event.
    """
    if not STATE_FILE.exists():
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        STATE_FILE.touch()  # Create empty file
        print("Initialized water pump history file (JSONL)")


def append_event_to_disk(event: Dict[str, Any]):
    """
    Append a single event to the JSONL file (append-only, never deletes history).
    Each line is a complete JSON object representing one watering event.
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
    Load recent water history from JSONL file into memory.
    Only loads events from last 24 hours to keep memory bounded.
    Full history remains in file forever for long-term analysis.

    Performance: Reads entire file and filters by timestamp. For a 6-month
    experiment with ~40k lines, expect <2 seconds to read. Since restarts
    are infrequent, this is acceptable. If optimization needed, could use
    file-read-backwards (https://pypi.org/project/file-read-backwards/) to
    read only the most recent lines.
    """
    global water_history
    try:
        initialize_state_file()

        if not STATE_FILE.exists() or STATE_FILE.stat().st_size == 0:
            water_history = deque()
            print("No existing water history found")
            return

        # Calculate cutoff time (24 hours ago)
        cutoff_time = datetime.now() - timedelta(hours=24)

        # Read JSONL file and load only recent events
        # Note: Reads full file then filters. Fast enough for infrequent restarts.
        recent_events = deque()
        with open(STATE_FILE, 'r') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue

                try:
                    event = json.loads(line)
                    event_time = datetime.fromisoformat(event["timestamp"])

                    # Only load events from last 24h into memory
                    if event_time >= cutoff_time:
                        recent_events.append(event)
                except (json.JSONDecodeError, KeyError, ValueError) as e:
                    print(f"Warning: Skipping malformed line in history: {e}")
                    continue

        water_history = recent_events
        print(f"Loaded {len(water_history)} recent water events from disk (last 24h)")

    except Exception as e:
        print(f"Error: Failed to load water pump history: {e}")
        # Return safe defaults if loading fails
        water_history = deque()


def ensure_state_loaded():
    """
    Ensure state has been loaded from disk on first tool invocation.
    This is called by each tool before accessing water_history.
    """
    global _state_loaded

    if not _state_loaded:
        _state_loaded = True
        load_state()


def prune_water_history():
    """
    Remove events older than 24 hours from water_history deque.
    This keeps memory usage bounded and improves query performance.
    """
    if not water_history:
        return

    cutoff_time = datetime.now() - timedelta(hours=24)
    # Efficiently pop from left until within cutoff
    while water_history and datetime.fromisoformat(water_history[0]["timestamp"]) < cutoff_time:
        water_history.popleft()


def get_usage_last_24h() -> tuple[int, int]:
    """
    Calculate water usage in the last 24 hours.
    Prunes old events for efficiency.
    Returns: (total_ml_used, number_of_events)
    """
    if not water_history:
        return 0, 0

    # Prune old events before calculating
    prune_water_history()

    cutoff_time = datetime.now() - timedelta(hours=24)
    total_ml = 0
    count = 0
    # All events in deque should now be within 24h, but double-check
    for event in reversed(water_history):
        event_time = datetime.fromisoformat(event["timestamp"])
        if event_time <= cutoff_time:
            break
        total_ml += event["ml"]
        count += 1
    return total_ml, count


def setup_water_pump_tools(mcp: FastMCP):
    """Set up water pump tools on the MCP server"""

    @mcp.tool()
    async def dispense(
        ml: int = Field(
            ...,
            description=f"Amount to dispense in ml ({MIN_ML_PER_DISPENSE}-{MAX_ML_PER_DISPENSE})",
            ge=MIN_ML_PER_DISPENSE,
            le=MAX_ML_PER_DISPENSE
        )
    ) -> WaterDispenseResponse:
        """
        Dispense water to the plant.
        Accepts 10-100ml per dispense.
        Limited to 500ml per rolling 24 hour period.
        """
        # Ensure state has been loaded from disk
        ensure_state_loaded()

        # Check if plant status has been written first
        if not current_cycle_status["written"]:
            raise ValueError("Must call write_status first before dispensing water")

        # Check 24h usage limit
        used_24h, _ = get_usage_last_24h()
        remaining = MAX_ML_PER_24H - used_24h

        if remaining <= 0:
            raise ValueError(f"Daily water limit of {MAX_ML_PER_24H}ml already reached. Try again later.")

        # Dispense only what's allowed
        actual_ml = min(ml, remaining)

        # Record the dispensing event
        timestamp = datetime.now().isoformat()
        event = {
            "timestamp": timestamp,
            "ml": actual_ml
        }
        water_history.append(event)

        # Append event to disk (keeps full history forever)
        append_event_to_disk(event)

        return WaterDispenseResponse(
            dispensed=actual_ml,
            remaining_24h=remaining - actual_ml,
            timestamp=timestamp
        )

    @mcp.tool()
    async def get_usage_24h() -> WaterUsageResponse:
        """
        Get water usage statistics for the last 24 hours.
        Returns total ml used, remaining ml available, and number of watering events.
        """
        # Ensure state has been loaded from disk
        ensure_state_loaded()

        used_ml, events = get_usage_last_24h()
        remaining_ml = MAX_ML_PER_24H - used_ml

        return WaterUsageResponse(
            used_ml=used_ml,
            remaining_ml=remaining_ml,
            events=events
        )
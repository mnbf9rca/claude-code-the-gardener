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

# Constants
MAX_ML_PER_24H = 500  # Maximum water allowed in 24 hours
MIN_ML_PER_DISPENSE = 10  # Minimum amount per dispense
MAX_ML_PER_DISPENSE = 100  # Maximum amount per dispense

# State persistence
STATE_FILE = Path(__file__).parent.parent / "data" / "water_pump_state.json"

# Storage for water dispensing history
water_history = []  # List of {timestamp, ml} dictionaries

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


# State Persistence Functions
def initialize_state_file():
    """
    Ensure state file exists with safe defaults.
    Missing file = assume no watering history.
    """
    if not STATE_FILE.exists():
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        default_state = {
            "water_history": []
        }
        with open(STATE_FILE, 'w') as f:
            json.dump(default_state, f, indent=2)
        print("Initialized water pump state file with empty history")


def save_state():
    """Save water history to disk for persistence across restarts"""
    try:
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(STATE_FILE, 'w') as f:
            json.dump({"water_history": water_history}, f, indent=2)
    except Exception as e:
        print(f"Warning: Failed to save water pump state: {e}")


def load_state():
    """
    Load persisted water history from disk.
    Always returns a valid history list (initializes file if missing).
    """
    global water_history
    try:
        initialize_state_file()
        with open(STATE_FILE, 'r') as f:
            data = json.load(f)
            water_history = data.get("water_history", [])
            print(f"Loaded {len(water_history)} water dispensing events from disk")
    except Exception as e:
        print(f"Error: Failed to load water pump state: {e}")
        # Return safe defaults if loading fails
        water_history = []


def ensure_state_loaded():
    """
    Ensure state has been loaded from disk on first tool invocation.
    This is called by each tool before accessing water_history.
    """
    global _state_loaded

    if not _state_loaded:
        _state_loaded = True
        load_state()


def get_usage_last_24h() -> tuple[int, int]:
    """Calculate water usage in the last 24 hours
    Returns: (total_ml_used, number_of_events)
    """
    if not water_history:
        return 0, 0

    cutoff_time = datetime.now() - timedelta(hours=24)
    # Iterate from the end for efficiency, since new events are appended
    total_ml = 0
    count = 0
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
        water_history.append({
            "timestamp": timestamp,
            "ml": actual_ml
        })

        # Persist state to disk
        save_state()

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
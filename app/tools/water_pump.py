"""
Water Pump Tool - Dispense water with daily usage limits
Mock implementation for now, will integrate with ESP32 pump later.
"""
from datetime import datetime, timezone
from pydantic import BaseModel, Field
from fastmcp import FastMCP
from shared_state import current_cycle_status
from pathlib import Path
from utils.jsonl_history import JsonlHistory

# Constants
MAX_ML_PER_24H = 500  # Maximum water allowed in 24 hours
MIN_ML_PER_DISPENSE = 10  # Minimum amount per dispense
MAX_ML_PER_DISPENSE = 100  # Maximum amount per dispense

# State persistence (JSONL format for append-only writes)
STATE_FILE = Path(__file__).parent.parent / "data" / "water_pump_history.jsonl"

# History manager
water_history = JsonlHistory(file_path=STATE_FILE, max_memory_entries=1000)


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


def get_usage_last_24h() -> tuple[int, int]:
    """
    Calculate water usage in the last 24 hours.
    Returns: (total_ml_used, number_of_events)
    """
    # Get events from last 24 hours using utility
    recent_events = water_history.get_by_time_window(hours=24)

    if not recent_events:
        return 0, 0

    # Sum up the ml from all events with defensive handling
    total_ml = 0
    for event in recent_events:
        ml_value = event.get("ml", 0)
        # Ensure the value is numeric and convert to int
        if isinstance(ml_value, (int, float)) and ml_value > 0:
            total_ml += int(ml_value)

    count = len(recent_events)

    return total_ml, count


def setup_water_pump_tools(mcp: FastMCP):
    """Set up water pump tools on the MCP server"""

    @mcp.tool()
    async def dispense_water(
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
        timestamp = datetime.now(timezone.utc).isoformat()
        event = {
            "timestamp": timestamp,
            "ml": actual_ml
        }

        # Append to history (handles both memory and disk)
        water_history.append(event)

        return WaterDispenseResponse(
            dispensed=actual_ml,
            remaining_24h=remaining - actual_ml,
            timestamp=timestamp
        )

    @mcp.tool()
    async def get_water_usage_24h() -> WaterUsageResponse:
        """
        Get water usage statistics for the last 24 hours.
        Returns total ml used, remaining ml available, and number of watering events.
        """
        used_ml, events = get_usage_last_24h()
        remaining_ml = MAX_ML_PER_24H - used_ml

        return WaterUsageResponse(
            used_ml=used_ml,
            remaining_ml=remaining_ml,
            events=events
        )

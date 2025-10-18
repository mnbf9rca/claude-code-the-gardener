"""
Water Pump Tool - Dispense water with daily usage limits
Mock implementation for now, will integrate with ESP32 pump later.
"""
from typing import Dict, Any
from datetime import datetime, timedelta
from pydantic import BaseModel, Field, field_validator
from fastmcp import FastMCP
from shared_state import current_cycle_status

# Constants
MAX_ML_PER_24H = 500  # Maximum water allowed in 24 hours
MIN_ML_PER_DISPENSE = 10  # Minimum amount per dispense
MAX_ML_PER_DISPENSE = 100  # Maximum amount per dispense

# Storage for water dispensing history
water_history = []  # List of {timestamp, ml} dictionaries


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
    """Calculate water usage in the last 24 hours
    Returns: (total_ml_used, number_of_events)
    """
    if not water_history:
        return 0, 0

    cutoff_time = datetime.now() - timedelta(hours=24)
    recent_events = [
        event for event in water_history
        if datetime.fromisoformat(event["timestamp"]) > cutoff_time
    ]

    total_ml = sum(event["ml"] for event in recent_events)
    return total_ml, len(recent_events)


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

        # Clean up old history (keep 48 hours worth for safety)
        cutoff_time = datetime.now() - timedelta(hours=48)
        water_history[:] = [
            event for event in water_history
            if datetime.fromisoformat(event["timestamp"]) > cutoff_time
        ]

        # Update moisture sensor mock value if available
        try:
            import tools.moisture_sensor as ms_module
            # Each 10ml increases sensor reading by ~50-80 points
            increase = (actual_ml // 10) * 65  # Average of 50-80
            ms_module.mock_sensor_value = min(3500, ms_module.mock_sensor_value + increase)
        except:
            pass  # Ignore if moisture sensor not available

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
        used_ml, events = get_usage_last_24h()
        remaining_ml = MAX_ML_PER_24H - used_ml

        return WaterUsageResponse(
            used_ml=used_ml,
            remaining_ml=remaining_ml,
            events=events
        )
"""
Water Pump Tool - Dispense water with daily usage limits
Integrates with ESP32 pump via HTTP API with ML-to-seconds conversion.
"""
from datetime import datetime, timezone
import os
import httpx
from pydantic import BaseModel, Field
from fastmcp import FastMCP
from utils.shared_state import current_cycle_status
from utils.jsonl_history import JsonlHistory
from utils.paths import get_app_dir

# Constants
MAX_ML_PER_24H = 500  # Maximum water allowed in 24 hours
MIN_ML_PER_DISPENSE = 10  # Minimum amount per dispense
MAX_ML_PER_DISPENSE = 100  # Maximum amount per dispense

# ESP32 configuration from environment
ESP32_HOST = os.getenv("ESP32_HOST", "192.168.1.100")
ESP32_PORT = int(os.getenv("ESP32_PORT", "80"))
ESP32_BASE_URL = f"http://{ESP32_HOST}:{ESP32_PORT}"

# Pump calibration - ML dispensed per second of pump operation
# This value should be calibrated by running the pump for a known duration
# and measuring the water dispensed (e.g., run for 10s, measure 35ml = 3.5 ml/s)
PUMP_ML_PER_SECOND = float(os.getenv("PUMP_ML_PER_SECOND", "3.5"))

# HTTP client timeout (seconds)
HTTP_TIMEOUT = 10.0  # Longer timeout since pump operations take time

# State persistence (JSONL format for append-only writes)
STATE_FILE = get_app_dir("data") / "water_pump_history.jsonl"

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
        Dispense water to the plant via ESP32 pump controller.
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

        # Convert ML to seconds based on calibrated pump rate
        seconds = round(actual_ml / PUMP_ML_PER_SECOND, 1)

        # Ensure we're within ESP32 safety limits (1-30 seconds)
        if seconds < 1:
            seconds = 1
        elif seconds > 30:
            raise ValueError(f"Requested {actual_ml}ml requires {seconds}s, exceeds ESP32 safety limit (30s)")

        try:
            # Call ESP32 HTTP API to activate pump
            async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
                response = await client.post(
                    f"{ESP32_BASE_URL}/pump",
                    json={"seconds": int(seconds)},
                    headers={"Content-Type": "application/json"}
                )
                response.raise_for_status()
                data = response.json()

            # Verify ESP32 successfully activated pump
            if not data.get("success", False):
                raise ValueError(f"ESP32 pump activation failed: {data.get('error', 'Unknown error')}")

        except httpx.TimeoutException:
            raise ValueError(f"ESP32 timeout: No response from {ESP32_BASE_URL} within {HTTP_TIMEOUT}s")
        except httpx.HTTPStatusError as e:
            error_msg = e.response.text
            try:
                error_data = e.response.json()
                error_msg = error_data.get("error", error_msg)
            except:
                pass
            raise ValueError(f"ESP32 HTTP error ({e.response.status_code}): {error_msg}")
        except httpx.RequestError as e:
            raise ValueError(f"ESP32 connection error: Cannot reach {ESP32_BASE_URL} - {str(e)}")

        # Record the dispensing event (only after successful ESP32 activation)
        timestamp = datetime.now(timezone.utc).isoformat()
        event = {
            "timestamp": timestamp,
            "ml": actual_ml,
            "seconds": seconds
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

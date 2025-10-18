"""
Moisture Sensor Tool - Reads soil moisture levels
For now, returns mock data. Will integrate with ESP32 later.
"""
from typing import Dict, Any
from datetime import datetime
import random
from pydantic import BaseModel, Field
from fastmcp import FastMCP
from shared_state import current_cycle_status


class MoistureReading(BaseModel):
    """Response from moisture sensor"""
    value: int = Field(..., description="Raw sensor reading (0-4095 for ESP32 ADC)")
    timestamp: str = Field(..., description="ISO8601 timestamp of reading")
    status: str = Field(..., description="Sensor status")


# Store recent readings for history
sensor_history = []

# Mock sensor state - starts at moderate moisture
mock_sensor_value = 2000


def setup_moisture_sensor_tools(mcp: FastMCP):
    """Set up moisture sensor tools on the MCP server"""

    @mcp.tool()
    async def read_moisture() -> MoistureReading:
        """
        Read current moisture level from the sensor.
        Returns raw ADC value (0-4095).
        Lower values = drier soil, Higher values = wetter soil.
        Typical range: 1500 (dry) to 3000 (wet)
        """
        global mock_sensor_value

        # Simulate natural moisture decline over time
        # and add some realistic noise
        mock_sensor_value = max(
            1500,  # Don't go below very dry
            mock_sensor_value - random.randint(5, 15) + random.randint(0, 5)
        )

        timestamp = datetime.now().isoformat()
        reading = MoistureReading(
            value=mock_sensor_value,
            timestamp=timestamp,
            status="ok"
        )

        # Store in history
        sensor_history.append({
            "value": mock_sensor_value,
            "timestamp": timestamp
        })

        # Keep history limited
        if len(sensor_history) > 1440:  # ~24 hours at 1 reading/minute
            sensor_history.pop(0)

        return reading

    @mcp.tool()
    async def get_sensor_history(
        hours: int = Field(24, description="Number of hours of history to return")
    ) -> list[Dict[str, Any]]:
        """
        Get historical moisture sensor readings.
        Returns array of [timestamp, value] pairs at 10-minute intervals.
        """
        # For mock data, return last N entries based on hours requested
        # In production, this would query actual stored data
        entries_needed = hours * 6  # 6 readings per hour (every 10 min)

        if not sensor_history:
            return []

        # Sample the history at intervals if we have too many points
        if len(sensor_history) <= entries_needed:
            return sensor_history[-entries_needed:]

        # Sample evenly from available history
        step = len(sensor_history) // entries_needed
        sampled = []
        indices = list(range(0, len(sensor_history), step))[:entries_needed]
        for i in indices:
            reading = sensor_history[i]
            sampled.append([reading["timestamp"], reading["value"]])
        return sampled
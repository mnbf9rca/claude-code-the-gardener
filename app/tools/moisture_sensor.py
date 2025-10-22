"""
Moisture Sensor Tool - Reads soil moisture levels from ESP32 via HTTP
"""
from typing import Any
from datetime import datetime, timezone
import os
from urllib.parse import urlunparse
import httpx
from pydantic import BaseModel, Field
from fastmcp import FastMCP


class MoistureReading(BaseModel):
    """Response from moisture sensor"""
    value: int = Field(..., description="Raw sensor reading (0-4095 for ESP32 ADC)")
    timestamp: str = Field(..., description="ISO8601 timestamp of reading")
    status: str = Field(..., description="Sensor status")


# Store recent readings for history
# Note: Thread-safety is not needed here as MCP server runs in a single-threaded
# async event loop. All accesses to this list are via async functions that won't
# execute concurrently within the same event loop.
sensor_history = []

# ESP32 configuration from environment
ESP32_HOST = os.getenv("ESP32_HOST")
if not ESP32_HOST:
    raise ValueError("ESP32_HOST environment variable is required but not set")

ESP32_PORT = int(os.getenv("ESP32_PORT", "80"))

# Construct base URL properly using urllib
# Strip any protocol prefix from host if present
esp32_host_clean = ESP32_HOST.removeprefix("http://").removeprefix("https://")
# Remove any port suffix from host if present
if ":" in esp32_host_clean:
    esp32_host_clean = esp32_host_clean.split(":")[0]

ESP32_BASE_URL = urlunparse(("http", f"{esp32_host_clean}:{ESP32_PORT}", "", "", "", ""))

# HTTP client timeout (seconds)
HTTP_TIMEOUT = 5.0


def setup_moisture_sensor_tools(mcp: FastMCP):
    """Set up moisture sensor tools on the MCP server"""

    @mcp.tool()
    async def read_moisture() -> MoistureReading:
        """
        Read current moisture level from the sensor via ESP32 HTTP API.
        Returns raw ADC value (0-4095).
        Lower values = drier soil, Higher values = wetter soil.
        Typical range: 1500 (dry) to 3000 (wet)
        """
        try:
            # Call ESP32 HTTP API
            async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
                response = await client.get(f"{ESP32_BASE_URL}/moisture")
                response.raise_for_status()
                data = response.json()

            # Extract values from ESP32 response
            value = data["value"]
            # Use ESP32's timestamp if available, otherwise use current time
            timestamp = data.get("timestamp", datetime.now(timezone.utc).isoformat())
            status = data.get("status", "ok")

            reading = MoistureReading(
                value=value,
                timestamp=timestamp,
                status=status
            )

            # Store in history
            sensor_history.append({
                "value": value,
                "timestamp": timestamp
            })

            # Keep history limited
            if len(sensor_history) > 1440:  # ~24 hours at 1 reading/minute
                sensor_history.pop(0)

            return reading

        except httpx.TimeoutException as e:
            raise ValueError(f"ESP32 timeout: No response from {ESP32_BASE_URL} within {HTTP_TIMEOUT}s") from e
        except httpx.HTTPStatusError as e:
            raise ValueError(f"ESP32 HTTP error: {e.response.status_code} - {e.response.text}") from e
        except httpx.RequestError as e:
            raise ValueError(f"ESP32 connection error: Cannot reach {ESP32_BASE_URL} - {str(e)}") from e
        except (KeyError, ValueError) as e:
            raise ValueError(f"ESP32 response error: Invalid JSON format - {str(e)}") from e

    @mcp.tool()
    async def get_moisture_history(
        hours: int = Field(24, description="Number of hours of history to return")
    ) -> list[list[Any]]:
        """
        Get historical moisture sensor readings.
        Returns array of [timestamp, value] pairs at 10-minute intervals.

        Note: Internal storage uses dict format for consistency with JSONL persistence,
        but API returns [timestamp, value] pairs for easier plotting/visualization.
        """
        entries_needed = hours * 6  # 6 readings per hour (every 10 min)

        if not sensor_history:
            return []

        # Return all available entries if we don't have enough
        if len(sensor_history) <= entries_needed:
            return [[r["timestamp"], r["value"]] for r in sensor_history[-entries_needed:]]

        # Sample evenly from available history
        # Ensure step is at least 1 to avoid division by zero or infinite loops
        step = max(1, len(sensor_history) // entries_needed)
        sampled = []
        indices = list(range(0, len(sensor_history), step))[:entries_needed]
        for i in indices:
            reading = sensor_history[i]
            sampled.append([reading["timestamp"], reading["value"]])
        return sampled
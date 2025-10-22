"""
Moisture Sensor Tool - Reads soil moisture levels from ESP32 via HTTP
"""
from typing import Any
from datetime import datetime, timezone
import json
import httpx
from pydantic import BaseModel, Field
from fastmcp import FastMCP
from utils.esp32_config import get_esp32_config
from utils.jsonl_history import JsonlHistory
from utils.paths import get_app_dir


class MoistureReading(BaseModel):
    """Response from moisture sensor"""
    value: int = Field(..., description="Raw sensor reading (0-4095 for ESP32 ADC)")
    timestamp: str = Field(..., description="ISO8601 timestamp of reading")
    status: str = Field(..., description="Sensor status")


# State persistence - JSONL format for append-only history
# Keeps 10,000 readings in memory (~7 days at 1/min), unlimited on disk
sensor_history = JsonlHistory(
    file_path=get_app_dir("data") / "moisture_sensor_history.jsonl",
    max_memory_entries=10000
)

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
        # Get ESP32 config lazily (only when needed)
        esp32_config = get_esp32_config()

        try:
            # Call ESP32 HTTP API
            async with esp32_config.get_client(timeout=HTTP_TIMEOUT) as client:
                response = await client.get("/moisture")
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

            # Store in history (JsonlHistory handles memory limits and disk persistence)
            sensor_history.append({
                "value": value,
                "timestamp": timestamp
            })

            return reading

        except httpx.TimeoutException as e:
            raise ValueError(f"ESP32 timeout: No response from {esp32_config.base_url} within {HTTP_TIMEOUT}s") from e
        except httpx.HTTPStatusError as e:
            raise ValueError(f"ESP32 HTTP error: {e.response.status_code} - {e.response.text}") from e
        except httpx.RequestError as e:
            raise ValueError(f"ESP32 connection error: Cannot reach {esp32_config.base_url} - {str(e)}") from e
        except KeyError as e:
            raise ValueError(f"ESP32 response error: Missing expected key in JSON - {str(e)}") from e
        except json.JSONDecodeError as e:
            raise ValueError(f"ESP32 response error: Invalid JSON format - {str(e)}") from e

    @mcp.tool()
    async def get_moisture_history(
        hours: int = Field(24, description="Number of hours of history to return")
    ) -> list[list[Any]]:
        """
        Get moisture sensor readings from the last N hours.
        Returns up to 6 samples per hour (e.g., 144 for 24 hours).
        Samples are evenly distributed across time using time-bucketed sampling.

        Returns array of [timestamp, value] pairs for plotting/visualization.
        """
        # Use time-bucketed sampling for proper temporal distribution
        sampled_readings = sensor_history.get_time_bucketed_sample(
            hours=hours,
            samples_per_hour=6,
            timestamp_key="timestamp",
            aggregation="middle"  # Use reading closest to bucket center
        )

        # Convert to [timestamp, value] format for API
        return [[r["timestamp"], r["value"]] for r in sampled_readings]
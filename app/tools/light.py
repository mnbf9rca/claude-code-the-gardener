"""
Light Tool - Control grow light with timing constraints
Integrates with Meross smart plug via Home Assistant HTTP API
"""
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
from pydantic import BaseModel, Field
from fastmcp import FastMCP
from shared_state import current_cycle_status
import httpx
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Constants
MIN_ON_MINUTES = 30  # Minimum time light can be on
MAX_ON_MINUTES = 120  # Maximum time light can be on (2 hours)
MIN_OFF_MINUTES = 30  # Minimum time between activations

# Home Assistant Configuration
HA_URL = os.getenv("HOME_ASSISTANT_URL", "http://homeassistant.local:8123")
HA_TOKEN = os.getenv("HOME_ASSISTANT_TOKEN", "")
LIGHT_ENTITY_ID = os.getenv("LIGHT_ENTITY_ID", "switch.smart_plug_mini")

# HTTP client for Home Assistant
http_client: Optional[httpx.AsyncClient] = None

def get_http_client() -> httpx.AsyncClient:
    """Get or create the HTTP client for Home Assistant"""
    global http_client
    if http_client is None:
        http_client = httpx.AsyncClient(
            timeout=10.0,
            headers={"Authorization": f"Bearer {HA_TOKEN}"}
        )
    return http_client

# Light state
light_state = {
    "status": "off",
    "last_on": None,  # ISO timestamp
    "last_off": None,  # ISO timestamp
    "scheduled_off": None,  # ISO timestamp when light will turn off
}


class LightActivationResponse(BaseModel):
    """Response from turning on the light"""
    status: str = Field(..., description="Current light status (on/off)")
    duration_minutes: int = Field(..., description="How long the light will be on")
    off_at: str = Field(..., description="ISO timestamp when light will turn off")


class LightStatusResponse(BaseModel):
    """Response from checking light status"""
    status: str = Field(..., description="Current light status (on/off)")
    last_on: Optional[str] = Field(None, description="ISO timestamp of last activation")
    last_off: Optional[str] = Field(None, description="ISO timestamp of last deactivation")
    can_activate: bool = Field(..., description="Whether light can be activated now")
    minutes_until_available: int = Field(..., description="Minutes until light can be activated (0 if available)")


def check_light_availability() -> tuple[bool, int]:
    """
    Check if light can be activated now.
    Returns: (can_activate, minutes_until_available)
    """
    # If light is currently on, it cannot be activated again
    if light_state["status"] == "on":
        if light_state["scheduled_off"]:
            remaining = (
                datetime.fromisoformat(light_state["scheduled_off"]) - datetime.now()
            ).total_seconds() / 60
            return False, max(1, int(remaining))
        return False, 0

    # If light has never been on, it can be activated
    if not light_state["last_off"]:
        return True, 0

    # Check if minimum off time has elapsed
    last_off_time = datetime.fromisoformat(light_state["last_off"])
    time_since_off = (datetime.now() - last_off_time).total_seconds() / 60

    if time_since_off >= MIN_OFF_MINUTES:
        return True, 0
    else:
        minutes_remaining = int(MIN_OFF_MINUTES - time_since_off)
        return False, max(1, minutes_remaining)


async def call_ha_service(service: str, entity_id: str) -> bool:
    """
    Call a Home Assistant service (turn_on or turn_off)
    Returns: True if successful, False otherwise
    """
    try:
        client = get_http_client()
        domain = entity_id.split(".")[0]  # Extract domain (e.g., 'switch' from 'switch.smart_plug_mini')
        url = f"{HA_URL}/api/services/{domain}/{service}"

        response = await client.post(
            url,
            json={"entity_id": entity_id}
        )
        response.raise_for_status()
        return True
    except Exception as e:
        print(f"Warning: Failed to call Home Assistant service {service}: {e}")
        return False


async def get_ha_entity_state(entity_id: str) -> Optional[str]:
    """
    Get the current state of a Home Assistant entity
    Returns: 'on', 'off', or None if unavailable
    """
    try:
        client = get_http_client()
        url = f"{HA_URL}/api/states/{entity_id}"

        response = await client.get(url)
        response.raise_for_status()
        data = response.json()
        return data.get("state")
    except Exception as e:
        print(f"Warning: Failed to get Home Assistant entity state: {e}")
        return None


def setup_light_tools(mcp: FastMCP):
    """Set up light control tools on the MCP server"""

    @mcp.tool()
    async def turn_on(
        minutes: int = Field(
            ...,
            description=f"Duration in minutes ({MIN_ON_MINUTES}-{MAX_ON_MINUTES})",
            ge=MIN_ON_MINUTES,
            le=MAX_ON_MINUTES
        )
    ) -> LightActivationResponse:
        """
        Activate the grow light for a specified duration.
        Accepts 30-120 minutes.
        Requires minimum 30 minutes off between activations.
        """
        # Check if plant status has been written first
        if not current_cycle_status["written"]:
            raise ValueError("Must call write_status first before controlling light")

        # Check if light can be activated
        can_activate, minutes_wait = check_light_availability()

        if not can_activate:
            if light_state["status"] == "on":
                raise ValueError(
                    f"Light is already on, will turn off at {light_state['scheduled_off']}. "
                    f"Wait {minutes_wait} minutes."
                )
            else:
                raise ValueError(
                    f"Light requires {MIN_OFF_MINUTES} minutes off between activations. "
                    f"Wait {minutes_wait} more minutes."
                )

        # Call Home Assistant to turn on the light
        success = await call_ha_service("turn_on", LIGHT_ENTITY_ID)
        if not success:
            raise ValueError("Failed to communicate with Home Assistant to turn on light")

        # Update local state
        now = datetime.now()
        off_time = now + timedelta(minutes=minutes)

        light_state["status"] = "on"
        light_state["last_on"] = now.isoformat()
        light_state["scheduled_off"] = off_time.isoformat()

        return LightActivationResponse(
            status="on",
            duration_minutes=minutes,
            off_at=off_time.isoformat()
        )

    @mcp.tool()
    async def turn_off() -> Dict[str, str]:
        """
        Manually turn off the grow light.
        This will turn off the light immediately regardless of scheduled duration.
        """
        # Check if plant status has been written first
        if not current_cycle_status["written"]:
            raise ValueError("Must call write_status first before controlling light")

        # Call Home Assistant to turn off the light
        success = await call_ha_service("turn_off", LIGHT_ENTITY_ID)
        if not success:
            raise ValueError("Failed to communicate with Home Assistant to turn off light")

        # Update local state
        now = datetime.now()
        light_state["status"] = "off"
        light_state["last_off"] = now.isoformat()
        light_state["scheduled_off"] = None

        return {
            "status": "off",
            "turned_off_at": now.isoformat(),
            "message": "Light turned off successfully"
        }

    @mcp.tool()
    async def get_light_status() -> LightStatusResponse:
        """
        Get current light status and availability.
        Returns whether light is on/off and when it can be activated next.
        Queries Home Assistant for real-time state.
        """
        # Query Home Assistant for actual state
        ha_state = await get_ha_entity_state(LIGHT_ENTITY_ID)

        # If HA is available, sync with actual state
        if ha_state is not None:
            light_state["status"] = ha_state

        # Check if scheduled off time has passed (auto turn off)
        if light_state["status"] == "on" and light_state["scheduled_off"]:
            if datetime.now() >= datetime.fromisoformat(light_state["scheduled_off"]):
                # Time to turn off the light
                await call_ha_service("turn_off", LIGHT_ENTITY_ID)
                light_state["status"] = "off"
                light_state["last_off"] = light_state["scheduled_off"]
                light_state["scheduled_off"] = None

        can_activate, minutes_wait = check_light_availability()

        return LightStatusResponse(
            status=light_state["status"],
            last_on=light_state["last_on"],
            last_off=light_state["last_off"],
            can_activate=can_activate,
            minutes_until_available=minutes_wait
        )
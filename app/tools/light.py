"""
Light Tool - Control grow light with timing constraints
Mock implementation for now, will integrate with Meross smart plug via Home Assistant later.
"""
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
from pydantic import BaseModel, Field
from fastmcp import FastMCP
from shared_state import current_cycle_status

# Constants
MIN_ON_MINUTES = 30  # Minimum time light can be on
MAX_ON_MINUTES = 120  # Maximum time light can be on (2 hours)
MIN_OFF_MINUTES = 30  # Minimum time between activations

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

        # Turn on the light
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
    async def get_light_status() -> LightStatusResponse:
        """
        Get current light status and availability.
        Returns whether light is on/off and when it can be activated next.
        """
        # Check if scheduled off time has passed (auto turn off simulation)
        if light_state["status"] == "on" and light_state["scheduled_off"]:
            if datetime.now() >= datetime.fromisoformat(light_state["scheduled_off"]):
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
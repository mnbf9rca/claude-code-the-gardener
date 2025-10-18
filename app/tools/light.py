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
import json
import asyncio
from pathlib import Path
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

# State persistence
STATE_FILE = Path(__file__).parent.parent / "data" / "light_state.json"

# Background task for scheduled turn-off
scheduled_task: Optional[asyncio.Task] = None

# Startup reconciliation flag
_reconciliation_done = False

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


# State Persistence Functions
def initialize_state_file():
    """
    Ensure state file exists with safe defaults.
    Missing file = assume safe state (off, no scheduled tasks).
    If state was 'on' it MUST have a scheduled_off, so missing file = off.
    """
    if not STATE_FILE.exists():
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        default_state = {
            "status": "off",
            "last_on": None,
            "last_off": None,
            "scheduled_off": None
        }
        with open(STATE_FILE, 'w') as f:
            json.dump(default_state, f, indent=2)
        print("Initialized light state file with safe defaults (off)")


def save_state():
    """Save light state to disk for crash recovery"""
    try:
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(STATE_FILE, 'w') as f:
            json.dump(light_state, f, indent=2)
    except Exception as e:
        print(f"Warning: Failed to save light state: {e}")


def load_state() -> Dict[str, Any]:
    """
    Load persisted light state from disk.
    Always returns a valid state dict (initializes file if missing).
    """
    try:
        initialize_state_file()
        with open(STATE_FILE, 'r') as f:
            return json.load(f)
    except Exception as e:
        print(f"Error: Failed to load light state: {e}")
        # Return safe defaults if loading fails
        return {
            "status": "off",
            "last_on": None,
            "last_off": None,
            "scheduled_off": None
        }


def clear_scheduled_state():
    """
    Clear only the scheduled_off field (keep history).
    File always remains - never deleted.
    """
    try:
        light_state["scheduled_off"] = None
        save_state()
    except Exception as e:
        print(f"Warning: Failed to clear scheduled state: {e}")


# Background Task Management
async def execute_scheduled_turn_off():
    """
    Background task that turns off the light at the scheduled time.
    This is the actual task that runs in the background.
    """
    global scheduled_task
    try:
        # Calculate how long to wait
        if not light_state["scheduled_off"]:
            print("Warning: No scheduled_off time set, cancelling task")
            return

        scheduled_time = datetime.fromisoformat(light_state["scheduled_off"])
        now = datetime.now()

        # If already past due, turn off immediately
        if now >= scheduled_time:
            wait_seconds = 0
        else:
            wait_seconds = (scheduled_time - now).total_seconds()

        print(f"Scheduled turn-off in {wait_seconds:.1f} seconds at {light_state['scheduled_off']}")

        # Wait until scheduled time
        if wait_seconds > 0:
            await asyncio.sleep(wait_seconds)

        # Turn off the light via Home Assistant
        print("Executing scheduled turn-off")
        success = await call_ha_service("turn_off", LIGHT_ENTITY_ID)

        if success:
            # Update state
            light_state["status"] = "off"
            light_state["last_off"] = datetime.now().isoformat()
            clear_scheduled_state()
            print(f"Light turned off successfully at scheduled time")
        else:
            print("Warning: Failed to turn off light via Home Assistant")

    except asyncio.CancelledError:
        print("Scheduled turn-off task was cancelled")
        raise
    except Exception as e:
        print(f"Error in scheduled turn-off task: {e}")
    finally:
        scheduled_task = None


def schedule_turn_off_task(off_time_iso: str):
    """
    Schedule a background task to turn off the light at the specified time.
    Cancels any existing scheduled task.
    """
    global scheduled_task

    # Cancel existing task if any
    cancel_scheduled_task()

    # Create new background task
    scheduled_task = asyncio.create_task(execute_scheduled_turn_off())
    print(f"Background task scheduled to turn off light at {off_time_iso}")


def cancel_scheduled_task():
    """Cancel the currently scheduled turn-off task if it exists"""
    global scheduled_task

    if scheduled_task and not scheduled_task.done():
        scheduled_task.cancel()
        print("Cancelled scheduled turn-off task")
        scheduled_task = None


# Startup Reconciliation
async def reconcile_state_on_startup():
    """
    Reconcile light state on server startup.
    Implements crash recovery by checking persisted state and reconciling with Home Assistant.

    Recovery strategy:
    1. If scheduled_off is in the past: turn off immediately (enforce schedule)
    2. If scheduled_off is in the future: reschedule task (resume plan)
    3. Always sync with Home Assistant actual state
    """
    print("=== Starting light state reconciliation ===")

    try:
        # Load persisted state
        persisted = load_state()
        light_state.update(persisted)
        print(f"Loaded persisted state: {persisted}")

        # Query Home Assistant for actual state
        actual_state = await get_ha_entity_state(LIGHT_ENTITY_ID)
        print(f"Home Assistant reports light is: {actual_state}")

        # Check if we have a scheduled off time
        if light_state["scheduled_off"]:
            scheduled_time = datetime.fromisoformat(light_state["scheduled_off"])
            now = datetime.now()

            if now >= scheduled_time:
                # Case 1: Scheduled time has passed - turn off immediately
                print(f"Scheduled off time {light_state['scheduled_off']} has passed. Enforcing schedule.")

                if actual_state == "on":
                    print("Light is still on, turning off now...")
                    success = await call_ha_service("turn_off", LIGHT_ENTITY_ID)
                    if success:
                        light_state["status"] = "off"
                        light_state["last_off"] = now.isoformat()
                        print("Light turned off successfully")
                    else:
                        print("Warning: Failed to turn off light")
                else:
                    print("Light is already off, updating state")
                    light_state["status"] = "off"

                # Clear the scheduled time since it's been handled
                clear_scheduled_state()

            else:
                # Case 2: Scheduled time is in the future - reschedule task
                remaining_seconds = (scheduled_time - now).total_seconds()
                print(f"Scheduled off time is in {remaining_seconds:.1f}s. Rescheduling task.")

                # Sync state with Home Assistant
                if actual_state == "on":
                    light_state["status"] = "on"
                    # Reschedule the turn-off task
                    schedule_turn_off_task(light_state["scheduled_off"])
                    print("Task rescheduled successfully")
                else:
                    # Light is off but was supposed to be on - might have been manually turned off
                    print("Warning: Light is off but had a scheduled turn-off. Clearing schedule.")
                    light_state["status"] = "off"
                    clear_scheduled_state()

        else:
            # No scheduled time - just sync with actual state
            print("No scheduled turn-off time. Syncing with Home Assistant.")
            if actual_state:
                light_state["status"] = actual_state
                save_state()

        print(f"=== Reconciliation complete. Final state: {light_state['status']} ===")

    except Exception as e:
        print(f"Error during state reconciliation: {e}")
        # On error, assume safe defaults
        light_state["status"] = "off"
        clear_scheduled_state()


async def ensure_reconciliation_done():
    """
    Ensure startup reconciliation has been run.
    Called by each tool on first invocation.
    """
    global _reconciliation_done

    if not _reconciliation_done:
        _reconciliation_done = True
        await reconcile_state_on_startup()


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
        # Ensure startup reconciliation has been done
        await ensure_reconciliation_done()

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

        # Persist state to disk for crash recovery
        save_state()

        # Schedule background task to turn off at specified time
        schedule_turn_off_task(off_time.isoformat())

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
        # Ensure startup reconciliation has been done
        await ensure_reconciliation_done()

        # Check if plant status has been written first
        if not current_cycle_status["written"]:
            raise ValueError("Must call write_status first before controlling light")

        # Cancel any scheduled turn-off task
        cancel_scheduled_task()

        # Call Home Assistant to turn off the light
        success = await call_ha_service("turn_off", LIGHT_ENTITY_ID)
        if not success:
            raise ValueError("Failed to communicate with Home Assistant to turn off light")

        # Update local state
        now = datetime.now()
        light_state["status"] = "off"
        light_state["last_off"] = now.isoformat()

        # Clear scheduled state (but keep state file)
        clear_scheduled_state()

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
        # Ensure startup reconciliation has been done
        await ensure_reconciliation_done()

        # Query Home Assistant for actual state
        ha_state = await get_ha_entity_state(LIGHT_ENTITY_ID)

        # If HA is available, sync with actual state
        if ha_state is not None:
            light_state["status"] = ha_state

        # Safety net: Check if scheduled off time has passed
        # (Background task should handle this, but this is defense-in-depth)
        if light_state["status"] == "on" and light_state["scheduled_off"]:
            if datetime.now() >= datetime.fromisoformat(light_state["scheduled_off"]):
                print("Warning: Scheduled off time passed but light still on (background task may have failed)")
                # Turn off as safety measure
                await call_ha_service("turn_off", LIGHT_ENTITY_ID)
                light_state["status"] = "off"
                light_state["last_off"] = datetime.now().isoformat()
                clear_scheduled_state()
                # Cancel task if it still exists
                cancel_scheduled_task()

        can_activate, minutes_wait = check_light_availability()

        return LightStatusResponse(
            status=light_state["status"],
            last_on=light_state["last_on"],
            last_off=light_state["last_off"],
            can_activate=can_activate,
            minutes_until_available=minutes_wait
        )
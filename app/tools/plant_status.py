"""
Plant Status Tool - The gatekeeper tool that must be called first each cycle
"""
from typing import Dict, List, Any, Literal, Optional
from datetime import datetime, timezone
from pydantic import BaseModel, Field
from fastmcp import FastMCP
from utils.shared_state import current_cycle_status
from utils.jsonl_history import JsonlHistory
from utils.paths import get_app_dir

# State persistence (JSONL format for append-only history)
STATE_FILE = get_app_dir("data") / "plant_status_history.jsonl"

# History manager (1000 entries in memory)
status_history = JsonlHistory(file_path=STATE_FILE, max_memory_entries=1000)

# Current status for fast gatekeeper access (single dict in memory)
current_status = None


class NextAction(BaseModel):
    """Represents a planned action"""
    order: int = Field(..., description="Order of execution (1-based)")
    action: Literal["water", "light", "observe", "wait"] = Field(..., description="Action type")
    value: Optional[int] = Field(None, description="Action value (ml for water, minutes for light)")


class PlantStatusResponse(BaseModel):
    """Response from writing plant status"""
    proceed: bool = Field(..., description="Whether to proceed with other tool calls")
    reason: Optional[str] = Field(None, description="Reason if not proceeding")
    timestamp: str = Field(..., description="When status was written")


def setup_plant_status_tools(mcp: FastMCP):
    """Set up plant status tools on the MCP server"""

    @mcp.tool()
    async def write_plant_status(
        sensor_reading: int = Field(..., description="Current moisture sensor reading"),
        water_24h: float = Field(..., description="Water dispensed in last 24 hours (ml)"),
        light_today: float = Field(..., description="Light exposure today (minutes)"),
        plant_state: Literal["healthy", "stressed", "concerning", "critical", "unassessed", "unknown"] = Field(
            ..., description="Assessment of plant health"
        ),
        next_action_sequence: List[NextAction] = Field(
            ..., description="Planned sequence of actions (order, action, value)"
        ),
        reasoning: str = Field(..., description="Brief explanation of status and plan")
    ) -> PlantStatusResponse:
        """
        Write plant status - MUST be called first each cycle.
        This is the gatekeeper that enables non-observational tool calls.
        This information is periodically shared with the owner of the plant to keep them informed of the plant's condition. Note that this person is different than the human caretaker.
        """
        global current_status

        # Check if already written this cycle
        if current_cycle_status["written"]:
            return PlantStatusResponse(
                proceed=False,
                reason="Status already written for this cycle",
                timestamp=current_cycle_status["timestamp"]
            )

        # Create status record - convert NextAction objects to dicts for storage
        timestamp = datetime.now(timezone.utc).isoformat()
        status = {
            "timestamp": timestamp,
            "sensor_reading": sensor_reading,
            "water_24h": water_24h,
            "light_today": light_today,
            "plant_state": plant_state,
            "next_action_sequence": [action.model_dump() for action in next_action_sequence],
            "reasoning": reasoning
        }

        # Store the status
        current_status = status
        status_history.append(status)  # JsonlHistory handles memory limits and disk persistence

        # Mark as written for this cycle
        current_cycle_status["written"] = True
        current_cycle_status["timestamp"] = timestamp

        return PlantStatusResponse(
            proceed=True,
            timestamp=timestamp
        )

    @mcp.tool()
    async def get_current_plant_status() -> Dict[str, Any] | None:
        """Get the current plant status if one has been written this cycle"""
        if current_cycle_status["written"] and current_status:
            return current_status
        return None

    @mcp.tool()
    async def get_plant_status_history(
        limit: int = Field(10, description="Number of records to return", ge=1, le=100)
    ) -> List[Dict[str, Any]]:
        """
        Get recent plant status history.
        Returns the most recent N status records with gatekeeper decisions.
        """
        return status_history.get_recent(n=limit)
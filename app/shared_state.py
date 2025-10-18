"""
Shared state management for the Plant Care MCP Server
"""
from datetime import datetime

# Track if plant status has been written this cycle
current_cycle_status = {"written": False, "timestamp": None}


def reset_cycle():
    """Reset cycle status - to be called at the start of each cron run"""
    current_cycle_status["written"] = False
    current_cycle_status["timestamp"] = datetime.now().isoformat()
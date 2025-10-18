"""
Plant Care MCP Server
Main server that composes all plant care tools
"""
import asyncio
from typing import Dict, List, Any
from fastmcp import FastMCP
from tools.plant_status import setup_plant_status_tools
from tools.moisture_sensor import setup_moisture_sensor_tools

# Initialize the MCP server
mcp = FastMCP("Plant Care System")

# In-memory storage for simple state management
plant_status_store: Dict[str, Any] = {}
action_log: List[Any] = []
thoughts_log: List[Any] = []

# Set up all tools
setup_plant_status_tools(mcp)
setup_moisture_sensor_tools(mcp)

if __name__ == "__main__":
    # For local testing
    print("Starting Plant Care MCP Server...")
    print("Run with: fastmcp run server:mcp")
    # The server will be started by fastmcp CLI
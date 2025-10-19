"""
Plant Care MCP Server
Main server that composes all plant care tools
"""
from fastmcp import FastMCP
from tools.plant_status import setup_plant_status_tools
from tools.moisture_sensor import setup_moisture_sensor_tools
from tools.water_pump import setup_water_pump_tools
from tools.light import setup_light_tools
from tools.camera import setup_camera_tools
from tools.thinking import setup_thinking_tools
from tools.action_log import setup_action_log_tools

# Initialize the MCP server
mcp = FastMCP("Plant Care System")

# Set up all tools
setup_plant_status_tools(mcp)
setup_moisture_sensor_tools(mcp)
setup_water_pump_tools(mcp)
setup_light_tools(mcp)
setup_camera_tools(mcp)
setup_thinking_tools(mcp)
setup_action_log_tools(mcp)

if __name__ == "__main__":
    # For local testing
    print("Starting Plant Care MCP Server...")
    print("Run with: fastmcp run server:mcp")
    # The server will be started by fastmcp CLI
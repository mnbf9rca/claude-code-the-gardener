"""
HTTP Server Runner for Plant Care MCP
Runs the MCP server with HTTP transport for remote access
"""
import os
from dotenv import load_dotenv
from server import mcp

# Load environment variables
load_dotenv()

# Get configuration from environment
HOST = os.getenv("MCP_HOST", "0.0.0.0")
PORT = int(os.getenv("MCP_PORT", "8000"))

def main():
    """Start the MCP server with HTTP transport"""
    print("=" * 60)
    print("🌱 Plant Care MCP Server - HTTP Mode")
    print("=" * 60)
    print(f"Server starting on http://{HOST}:{PORT}")
    print(f"MCP endpoint: http://{HOST}:{PORT}/mcp")
    print()
    print("Press Ctrl+C to stop")
    print("=" * 60)
    print()

    # Run the server with HTTP transport
    mcp.run(
        transport="http",
        host=HOST,
        port=PORT,
        path="/mcp"
    )

if __name__ == "__main__":
    main()

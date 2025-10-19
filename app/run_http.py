"""
HTTP Server Runner for Plant Care MCP
Runs the MCP server with HTTP transport for remote access
"""
import os
from dotenv import load_dotenv
from server import mcp
from utils.logging_config import get_logger

# Load environment variables
load_dotenv()

# Get logger
logger = get_logger(__name__)

# Get configuration from environment
HOST = os.getenv("MCP_HOST", "0.0.0.0")
PORT = int(os.getenv("MCP_PORT", "8000"))

def main():
    """Start the MCP server with HTTP transport"""
    logger.info("=" * 60)
    logger.info("🌱 Plant Care MCP Server - HTTP Mode")
    logger.info("=" * 60)
    logger.info(f"Server starting on http://{HOST}:{PORT}")
    logger.info(f"MCP endpoint: http://{HOST}:{PORT}/mcp")
    logger.info("Press Ctrl+C to stop")
    logger.info("=" * 60)

    # Run the server with HTTP transport
    mcp.run(
        transport="http",
        host=HOST,
        port=PORT,
        path="/mcp"
    )

if __name__ == "__main__":
    main()

"""
HTTP Server Runner for Plant Care MCP
Runs the MCP server with HTTP transport for remote access
"""
import os
from pathlib import Path
from dotenv import load_dotenv
import uvicorn
from starlette.staticfiles import StaticFiles
from server import mcp
from web_routes import add_message_routes
from utils.logging_config import get_logger

# Load environment variables
load_dotenv()

# Get logger
logger = get_logger(__name__)

# Get configuration from environment
HOST = os.getenv("MCP_HOST", "0.0.0.0")
PORT = int(os.getenv("MCP_PORT", "8000"))

# Photos directory - must match CAMERA_SAVE_PATH for consistency
PHOTOS_DIR = Path(os.getenv("CAMERA_SAVE_PATH", "./photos"))
# Handle relative paths relative to app directory
if not PHOTOS_DIR.is_absolute():
    PHOTOS_DIR = Path(__file__).parent / PHOTOS_DIR

# Create directory with explicit error handling
try:
    PHOTOS_DIR.mkdir(parents=True, exist_ok=True)
except Exception as e:
    import sys
    error_msg = f"Failed to create photos directory '{PHOTOS_DIR}': {e}"
    logger.error(error_msg)
    sys.exit(1)

def main():
    """Start the MCP server with HTTP transport"""
    logger.info("=" * 60)
    logger.info("🌱 Plant Care MCP Server - HTTP Mode")
    logger.info("=" * 60)
    logger.info(f"Server starting on http://{HOST}:{PORT}")
    logger.info(f"MCP endpoint: http://{HOST}:{PORT}/mcp")
    logger.info(f"Messages UI: http://{HOST}:{PORT}/messages")
    logger.info(f"Photos endpoint: http://{HOST}:{PORT}/photos/")
    logger.info("Press Ctrl+C to stop")
    logger.info("=" * 60)

    # Create the ASGI app with HTTP transport
    # This returns a Starlette app we can customize
    app = mcp.http_app(path="/mcp")

    # Mount static files to the Starlette app
    app.mount("/photos", StaticFiles(directory=str(PHOTOS_DIR)), name="photos")
    logger.info(f"Static files mounted: {PHOTOS_DIR}")

    # Add message routes (web UI and API)
    add_message_routes(app)
    logger.info("Message routes added")

    # Run uvicorn directly with the configured app
    uvicorn.run(app, host=HOST, port=PORT)

if __name__ == "__main__":
    main()

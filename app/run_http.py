"""
HTTP Server Runner for Plant Care MCP
Runs the MCP server with HTTP transport for remote access
"""
import os
import asyncio
from pathlib import Path
from datetime import datetime, timezone
from dotenv import load_dotenv
import uvicorn
import httpx
from starlette.staticfiles import StaticFiles
from server import mcp
from web_routes import add_message_routes
from admin_routes import add_admin_routes
from utils.logging_config import get_logger

# Load environment variables
load_dotenv()

# Get logger
logger = get_logger(__name__)

# Get configuration from environment
HOST = os.getenv("MCP_HOST", "0.0.0.0")
PORT = int(os.getenv("MCP_PORT", "8000"))
HEALTHCHECK_URL = os.getenv("HEALTHCHECK_URL")
HEALTHCHECK_INTERVAL_SECONDS = int(os.getenv("HEALTHCHECK_INTERVAL_SECONDS", "30"))

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

async def healthcheck_loop(url: str, interval_seconds: int):
    """
    Background task that sends healthcheck pings to healthchecks.io at regular intervals.

    Args:
        url: The healthchecks.io endpoint URL to ping
        interval_seconds: How often to send pings (in seconds)

    This task runs indefinitely, sending POST requests with timestamp payload.
    If the event loop is blocked or the server hangs, this task won't fire,
    causing healthchecks.io to alert on the missing pings.
    """
    logger.info(f"Healthcheck loop started, pinging every {interval_seconds} seconds: {url}")

    # Use context manager to ensure HTTP client cleanup
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            while True:
                try:
                    timestamp = datetime.now(timezone.utc).isoformat()
                    response = await client.post(url, json={"timestamp": timestamp})
                    response.raise_for_status()
                    logger.debug(f"Healthcheck ping successful: {response.status_code}")
                except httpx.HTTPStatusError as e:
                    # Server returned error status code (4xx/5xx)
                    logger.warning(f"Healthcheck ping failed: {e.response.status_code} {e.response.text}")
                except Exception as e:
                    # Network errors, timeouts, or other exceptions
                    logger.error(f"Healthcheck ping exception: {e}")

                # Wait before next ping
                await asyncio.sleep(interval_seconds)
        finally:
            logger.info("Healthcheck loop stopped")

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

    # Add admin routes (localhost-only administrative endpoints)
    add_admin_routes(app)
    logger.info("Admin routes added")

    # Set up healthcheck background task lifecycle
    @app.on_event("startup")
    async def start_healthcheck():
        """Start the healthcheck background task if HEALTHCHECK_URL is configured"""
        if HEALTHCHECK_URL:
            # Store task reference in app.state (Starlette best practice)
            app.state.healthcheck_task = asyncio.create_task(
                healthcheck_loop(HEALTHCHECK_URL, HEALTHCHECK_INTERVAL_SECONDS)
            )
            logger.info(f"✅ Healthcheck enabled: {HEALTHCHECK_URL} (interval: {HEALTHCHECK_INTERVAL_SECONDS}s)")
        else:
            logger.info("ℹ️  Healthcheck disabled (HEALTHCHECK_URL not set)")

    @app.on_event("shutdown")
    async def stop_healthcheck():
        """Stop the healthcheck background task gracefully"""
        # Retrieve task from app.state if it exists
        task = getattr(app.state, "healthcheck_task", None)
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                # Expected when task is cancelled
                # not using contextlib so as not to obscure other exceptions
                pass
            except Exception as exc:
                # Log any unexpected exceptions during shutdown
                logger.exception("Unexpected exception while cancelling healthcheck task: %s", exc)
            logger.info("Healthcheck task cancelled")

    # Run uvicorn directly with the configured app
    uvicorn.run(app, host=HOST, port=PORT)

if __name__ == "__main__":
    main()

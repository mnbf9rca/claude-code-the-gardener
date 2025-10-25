"""
Admin Routes for Plant Care System
Provides HTTP endpoints for administrative tasks (localhost-only, no auth)
"""
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.requests import Request
from utils.shared_state import reset_cycle
from utils.logging_config import get_logger

logger = get_logger(__name__)


async def post_reset_cycle(request: Request) -> JSONResponse:  # noqa: ARG001
    """
    POST /admin/reset-cycle
    Reset the gatekeeper cycle flag to allow new agent runs

    This endpoint is called by ExecStopPost in the systemd service
    to reset the gatekeeper after each agent run completes.

    Returns:
        JSON with success status
    """
    try:
        reset_cycle()
        logger.info("Cycle reset via admin endpoint")
        return JSONResponse({
            'success': True,
            'message': 'Cycle reset successfully'
        })
    except Exception as e:
        logger.error(f"Error resetting cycle: {e}")
        return JSONResponse(
            {'success': False, 'error': str(e)},
            status_code=500
        )


def add_admin_routes(app: Starlette):
    """
    Add admin routes to the Starlette app.

    Note: This function should only be called once during app initialization
    to avoid duplicate routes.

    Args:
        app: The Starlette application instance
    """
    # Define routes to add
    routes_to_add = [
        ('/admin/reset-cycle', post_reset_cycle, ['POST']),
    ]

    # Add routes using Starlette's built-in route management
    routes_added = 0
    for path, endpoint, methods in routes_to_add:
        try:
            # Starlette's add_route handles deduplication and route compilation
            app.add_route(path, endpoint, methods=methods)
            routes_added += 1
            logger.debug(f"Added route: {methods} {path}")
        except Exception as exc:
            # Route may already exist or other registration issue
            logger.warning(f"Could not add route {methods} {path}: {exc}")

    logger.info(f"Added {routes_added} admin routes to Starlette app")

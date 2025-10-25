"""
Admin Routes for Plant Care System
Provides HTTP endpoints for administrative tasks (localhost-only, no auth)
"""
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.requests import Request
from starlette.routing import Route
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
    # Define routes
    new_routes = [
        Route('/admin/reset-cycle', post_reset_cycle, methods=['POST']),
    ]

    # Check for existing routes to prevent duplicates
    existing_routes = set()
    for route in app.router.routes:
        path = getattr(route, 'path', None)
        methods = getattr(route, 'methods', None)
        if path and methods:
            for method in methods:
                existing_routes.add((path, method))

    # Add only new routes
    routes_added = 0
    for route in new_routes:
        route_exists = False
        if route.methods:
            route_exists = any(
                (route.path, method) in existing_routes
                for method in route.methods
            )

        if not route_exists:
            app.router.routes.append(route)
            routes_added += 1
        else:
            logger.warning(f"Route {route.path} {route.methods} already exists, skipping")

    logger.info(f"Added {routes_added} admin routes to Starlette app")

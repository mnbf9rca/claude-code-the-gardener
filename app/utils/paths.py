"""
Centralized path management for Plant Care MCP

Provides consistent directory path resolution with:
- Environment variable overrides for deployment flexibility
- Automatic directory creation
- Validation of directory types
- Support for both relative and absolute paths
"""
import os
from pathlib import Path
from utils.logging_config import get_logger

logger = get_logger(__name__)


def get_app_dir(dir_type: str) -> Path:
    """
    Get application directory path, creating it if needed.

    REQUIRED: Environment variable must be set. No default location provided.
    Supports both relative paths (relative to app root) and absolute paths.

    Args:
        dir_type: Directory type - must be one of the known types

    Returns:
        Path object for the directory (guaranteed to exist)

    Raises:
        ValueError: If dir_type is not recognized or required env var is missing

    Example:
        >>> # Set DATA_DIR=../data or DATA_DIR=/var/lib/plant-data in .env
        >>> data_dir = get_app_dir("data")  # Requires DATA_DIR env var
        >>> photos_dir = get_app_dir("photos")  # Requires CAMERA_SAVE_PATH env var
    """
    # Map directory types to required env var names
    config = {
        "data": "DATA_DIR",
        "photos": "CAMERA_SAVE_PATH",
    }

    # Validate dir_type
    if dir_type not in config:
        valid_types = ", ".join(sorted(config.keys()))
        raise ValueError(f"Unknown directory type '{dir_type}'. Valid types: {valid_types}")

    env_var = config[dir_type]
    path_str = os.getenv(env_var)

    # Require environment variable to be set
    if not path_str:
        raise ValueError(
            f"Required environment variable '{env_var}' is not set.\n"
            f"Data directories must be configured outside the application directory.\n"
            f"Add to .env file:\n"
            f"  {env_var}=../data  # Relative path (recommended)\n"
            f"  # or\n"
            f"  {env_var}=/var/lib/plant-care/data  # Absolute path"
        )

    path = Path(path_str)
    app_root = Path(__file__).parent.parent

    # If relative path, make it relative to app root
    if not path.is_absolute():
        path = app_root / path

    # Resolve to absolute path for comparison
    path_resolved = path.resolve()
    app_root_resolved = app_root.resolve()

    # Warn if path is inside app directory (allowed for testing, but discouraged)
    try:
        path_resolved.relative_to(app_root_resolved)
        logger.warning(
            f"⚠️  Directory '{path_resolved}' is inside the application directory.\n"
            f"   This is DISCOURAGED because install-mcp-server.sh deletes the app directory.\n"
            f"   Data will be lost on reinstall. Consider moving to: {app_root_resolved.parent / dir_type}\n"
            f"   Set {env_var}=../{dir_type} in .env to fix this."
        )
    except ValueError:
        # Path is outside app directory - this is good
        logger.debug(f"Directory {path_resolved} is outside app directory (recommended)")

    # Ensure directory exists
    try:
        path.mkdir(parents=True, exist_ok=True)
        logger.debug(f"Ensured directory exists: {path} (type={dir_type}, env_var={env_var})")
    except Exception as e:
        logger.error(f"Failed to create directory {path} for type '{dir_type}': {e}")
        raise

    return path

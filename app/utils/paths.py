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

    Checks environment variable override first, then uses default location.
    Supports both relative paths (relative to app root) and absolute paths.

    Args:
        dir_type: Directory type - must be one of the known types

    Returns:
        Path object for the directory (guaranteed to exist)

    Raises:
        ValueError: If dir_type is not recognized

    Example:
        >>> data_dir = get_app_dir("data")  # Checks DATA_DIR env var, defaults to app/data
        >>> photos_dir = get_app_dir("photos")  # Checks CAMERA_SAVE_PATH env var, defaults to app/photos
    """
    # Map directory types to (env_var_name, default_subdir)
    config = {
        "data": ("DATA_DIR", "data"),
        "photos": ("CAMERA_SAVE_PATH", "photos"),
    }

    # Validate dir_type
    if dir_type not in config:
        valid_types = ", ".join(sorted(config.keys()))
        raise ValueError(f"Unknown directory type '{dir_type}'. Valid types: {valid_types}")

    env_var, default_subdir = config[dir_type]
    path_str = os.getenv(env_var, default_subdir)
    path = Path(path_str)

    # If relative path, make it relative to app root
    if not path.is_absolute():
        app_root = Path(__file__).parent.parent
        path = app_root / path

    # Ensure directory exists
    try:
        path.mkdir(parents=True, exist_ok=True)
        logger.debug(f"Ensured directory exists: {path} (type={dir_type}, env_var={env_var})")
    except Exception as e:
        logger.error(f"Failed to create directory {path} for type '{dir_type}': {e}")
        raise

    return path

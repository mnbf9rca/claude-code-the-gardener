"""
Centralized logging configuration for Plant Care MCP

Provides consistent logging setup across all modules with:
- Configurable log levels via LOG_LEVEL environment variable
- Format optimized for journald/systemd integration
- Consistent logger access across modules
"""
import logging
import os
import sys


def setup_logging():
    """
    Configure logging for the application.

    Only configures if root logger has no handlers (i.e., not already configured).
    This respects any existing logging configuration from libraries like FastMCP.

    Log level is controlled by LOG_LEVEL environment variable.
    Defaults to INFO if not set.

    Valid levels: DEBUG, INFO, WARNING, ERROR, CRITICAL
    """
    log_level_str = os.getenv("LOG_LEVEL", "INFO").upper()
    log_level = getattr(logging, log_level_str, logging.INFO)

    # Only configure if not already configured
    root_logger = logging.getLogger()

    if not root_logger.handlers:
        # Configure root logger
        logging.basicConfig(
            level=log_level,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S',
            stream=sys.stdout
        )
    else:
        # Logging already configured (e.g., by FastMCP), just set our log level
        root_logger.setLevel(log_level)


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger for a specific module.

    Args:
        name: Logger name (typically __name__ from the calling module)

    Returns:
        Configured logger instance
    """
    return logging.getLogger(name)


# Initialize logging when module is imported
setup_logging()

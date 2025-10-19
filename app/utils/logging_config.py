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

    Log level is controlled by LOG_LEVEL environment variable.
    Defaults to INFO if not set.

    Valid levels: DEBUG, INFO, WARNING, ERROR, CRITICAL
    """
    log_level_str = os.getenv("LOG_LEVEL", "INFO").upper()
    log_level = getattr(logging, log_level_str, logging.INFO)

    # Configure root logger
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        stream=sys.stdout,
        force=True  # Override any existing configuration
    )


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

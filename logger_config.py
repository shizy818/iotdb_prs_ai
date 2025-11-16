#!/usr/bin/env python3
"""
Centralized logging configuration for the IoTDB PR analysis system
"""

import logging
import os
from pathlib import Path
from config import LOG_LEVEL, LOG_FORMAT, LOG_FILE, LOG_OUTPUT


def setup_logger(name: str) -> logging.Logger:
    """
    Set up a logger with configurable output options

    Args:
        name: The name of the module (usually __name__)

    Returns:
        logging.Logger: Configured logger instance
    """
    logger = logging.getLogger(name)

    # Only configure if not already configured
    if not logger.handlers:
        # Set the logging level from config
        level = getattr(logging, LOG_LEVEL.upper(), logging.INFO)
        logger.setLevel(level)

        # Create formatter
        formatter = logging.Formatter(LOG_FORMAT)

        # Check if we're in chat mode via environment variable
        chat_mode = os.getenv("CHAT_MODE", "false").lower() == "true"

        # Configure handlers based on mode and LOG_OUTPUT setting
        if chat_mode:
            # Chat mode: only output to file to avoid interfering with user interface
            output_mode = "file"
        else:
            # Normal mode: use the configured LOG_OUTPUT setting
            output_mode = LOG_OUTPUT.lower()

        if output_mode == "both":
            # Console handler
            console_handler = logging.StreamHandler()
            console_handler.setLevel(level)
            console_handler.setFormatter(formatter)
            logger.addHandler(console_handler)

            # File handler
            log_file_path = Path(LOG_FILE)
            log_file_path.parent.mkdir(parents=True, exist_ok=True)
            file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
            file_handler.setLevel(level)
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)

        elif output_mode == "console":
            # Only console handler
            console_handler = logging.StreamHandler()
            console_handler.setLevel(level)
            console_handler.setFormatter(formatter)
            logger.addHandler(console_handler)

        elif output_mode == "file":
            # Only file handler
            log_file_path = Path(LOG_FILE)
            log_file_path.parent.mkdir(parents=True, exist_ok=True)
            file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
            file_handler.setLevel(level)
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)

        else:
            # Default to both if invalid configuration
            console_handler = logging.StreamHandler()
            console_handler.setLevel(level)
            console_handler.setFormatter(formatter)
            logger.addHandler(console_handler)

            log_file_path = Path(LOG_FILE)
            log_file_path.parent.mkdir(parents=True, exist_ok=True)
            file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
            file_handler.setLevel(level)
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)

        # Prevent propagation to avoid duplicate logs
        logger.propagate = False

    return logger

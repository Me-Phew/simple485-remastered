"""A utility module for creating and configuring standard loggers.

This module provides a factory function, `get_custom_logger`, to simplify
the process of setting up a consistent logging structure across an application.
It includes support for console logging, general and error-specific logging
to separate rotated log files.
"""

import logging
import logging.handlers

# Default formatter for log messages written to files.
# Format: <LoggerName> <ThreadName>; <YYYY-MM-DD HH:MM:SS>; <LogLevel>; <Message>
default_file_log_formatter = logging.Formatter(
    "%(name)s %(threadName)s; %(asctime)s; %(levelname)s; %(message)s",
    "%Y-%m-%d %H:%M:%S",
)

# Default formatter for log messages written to the console (stream).
# Format: <LoggerName> <ThreadName>; <HH:MM:SS>; <LogLevel>; <Message>
default_stream_log_formatter = logging.Formatter(
    "%(name)s %(threadName)s; %(asctime)s; %(levelname)s; %(message)s",
    "%H:%M:%S",
)


def get_custom_logger(
    name: str,
    *,
    level: int,
    error_log_file_name: str = "simple485.error.log",
    log_file_name: str = "simple485.log",
    file_log_formatter: logging.Formatter = default_file_log_formatter,
    stream_log_formatter: logging.Formatter = default_stream_log_formatter,
    backup_count: int = 7,
    encoding: str = "utf-8",
) -> logging.Logger:
    """Sets up and returns a custom logger with file and stream handlers.

    This function configures a logger instance with three handlers:
    1.  A TimedRotatingFileHandler for general logs (INFO and above by default).
    2.  A TimedRotatingFileHandler specifically for ERROR level logs.
    3.  A StreamHandler for console output.

    Log files are rotated daily at midnight, and backups are kept for 7 days by default.
    To prevent duplication, handlers are only added if the logger does not
    already have them.

    Args:
        name (str): The name of the logger, typically `__name__`
        level (int): The minimum logging level for the logger (e.g., logging.INFO)
        error_log_file_name (str, optional): The file path for error logs
            Defaults to "simple485.error.log"
        log_file_name (str, optional): The file path for general logs
            Defaults to "simple485.log"
        file_log_formatter (logging.Formatter, optional): The formatter for
            file-based logs. Defaults to `default_file_log_formatter`
        stream_log_formatter (logging.Formatter, optional): The formatter for
            console-based logs. Defaults to `default_stream_log_formatter`
        backup_count (int, optional): The number of backup log files to keep.
            Defaults to 7
        encoding (str, optional): The encoding for log files
            Defaults to "utf-8"

    Returns:
        logging.Logger: A configured logger instance.
    """
    # Handler for writing ERROR level logs to a separate, rotated file.
    error_log_file_handler = logging.handlers.TimedRotatingFileHandler(
        error_log_file_name, when="midnight", backupCount=backup_count, encoding=encoding
    )
    error_log_file_handler.setFormatter(file_log_formatter)
    error_log_file_handler.setLevel(logging.ERROR)

    # Handler for writing all logs (at the specified level) to a general, rotated file.
    general_log_file_handler = logging.handlers.TimedRotatingFileHandler(
        log_file_name, when="midnight", backupCount=backup_count, encoding=encoding
    )
    general_log_file_handler.setFormatter(file_log_formatter)

    # Handler for writing logs to the console/stream (e.g., stdout).
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(stream_log_formatter)

    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Add handlers only if they haven't been added before to prevent duplicate logs.
    if not logger.handlers:
        logger.addHandler(general_log_file_handler)
        logger.addHandler(error_log_file_handler)
        logger.addHandler(stream_handler)

    return logger

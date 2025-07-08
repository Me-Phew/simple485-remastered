"""A collection of low-level, reusable utilities.

This module provides common helper classes and functions used throughout the
library, such as a byte-based Enum, a high-resolution
timestamp function, and unit conversion helpers.
"""

import time
from enum import Enum

from mephew_python_commons.logger_factory import LoggerFactory

logger_factory = LoggerFactory(
    log_files_prefix="simple485_remastered",
)


class ByteEnum(bytes, Enum):
    """A custom Enum base class where members are `bytes` objects.

    This allows for the creation of enumerations whose members are byte
    literals and behave like `bytes` objects, which is useful for defining
    protocol control characters.

    Example:
        class ControlChars(ByteEnum):
            SOH = b'\\x01'
            ETX = b'\\x03'

        assert ControlChars.SOH == b'\\x01'
        assert isinstance(ControlChars.SOH, bytes)
    """

    def __new__(cls, value):
        # This ensures the enum member is created as a `bytes` instance.
        return bytes.__new__(cls, value)


def get_milliseconds() -> int:
    """Returns the current system time as an integer number of milliseconds.

    This provides a high-resolution timestamp suitable for calculating
    timeouts and round-trip times within the communication protocol.

    Returns:
        int: The current time in milliseconds since the Epoch.
    """
    return int(round(time.time() * 1000))


def microseconds_to_seconds(microseconds: int | float) -> float:
    """Converts a value from microseconds to seconds.

    Args:
        microseconds (int | float): The time duration in microseconds.

    Returns:
        float: The equivalent time duration in seconds.
    """
    return microseconds * 1e-6

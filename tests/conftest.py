"""Shared Pytest Fixtures for Hardware Mocking.

This file provides fixtures that are automatically discovered by pytest. Its
primary purpose is to create a simulated hardware environment by mocking key
dependencies that would otherwise require a physical device.

The fixtures in this file mock:
- The `serial.Serial` port for communication.
- The `RPi.GPIO` module to prevent import errors on non-RPi systems.
- The `time.sleep` function to make tests run instantly.

Fixtures to mock `RPi.GPIO` and `time.sleep` are marked as `autouse=True`,
so they are automatically applied to all tests without needing to be explicitly
requested.
"""

import sys
from unittest.mock import MagicMock

import pytest


class MockSerial:
    """A mock `serial.Serial` object for testing communication without hardware.

    This class simulates a simple, loopback-style serial port. Data written
    via the `write` method is immediately appended to an internal buffer,
    making it available to be read via the `read` method on the same instance.

    This allows two components in a test (e.g., a Master and a Slave), both
    configured with the same `MockSerial` instance, to communicate with each other.
    """

    def __init__(self, *args, **kwargs):
        """Initializes the mock serial port."""
        self._read_buffer = bytearray()
        self._write_buffer = bytearray()  # Kept for potential future use (e.g., separate TX/RX)
        self.is_open = True
        self.in_waiting = 0

    def write(self, data: bytes) -> int:
        """Simulates writing data to the serial port.

        The written data is added to the internal read buffer.

        Args:
            data (bytes): The bytes to write.

        Returns:
            int: The number of bytes written.
        """
        # Data written by one device is available for any device to read.
        self._read_buffer.extend(data)
        self.in_waiting = len(self._read_buffer)
        return len(data)

    def read(self, size: int = 1) -> bytes:
        """Simulates reading data from the serial port.

        Consumes and returns the specified number of bytes from the internal buffer.

        Args:
            size (int): The number of bytes to read.

        Returns:
            bytes: The data read from the buffer.
        """
        data = self._read_buffer[:size]
        self._read_buffer = self._read_buffer[size:]
        self.in_waiting = len(self._read_buffer)
        return bytes(data)

    def flush(self):
        """Simulates flushing the write buffer. Does nothing."""
        pass

    def close(self):
        """Simulates closing the port."""
        self.is_open = False


@pytest.fixture
def mock_serial_port(mocker):
    """A pytest fixture that mocks the `serial.Serial` class.

    It replaces the actual `serial.Serial` with an instance of `MockSerial`.
    Any part of the code that tries to create a `serial.Serial` object will
    receive this single, shared mock instance instead.

    Yields:
        MockSerial: The shared mock serial port instance.
    """
    mock_port = MockSerial()
    mocker.patch("serial.Serial", return_value=mock_port)
    return mock_port


@pytest.fixture(autouse=True)
def mock_rpi_gpio(mocker):
    """An autouse fixture that mocks the `RPi.GPIO` module.

    This prevents `ImportError` when running tests on systems that are not a
    Raspberry Pi or do not have the RPi.GPIO library installed (e.g., developer
    machines, CI/CD environments). It replaces the module in `sys.modules`
    with a `MagicMock`, which absorbs any calls without error.
    """
    mock_gpio = MagicMock()
    sys.modules["RPi.GPIO"] = mock_gpio
    return mock_gpio


@pytest.fixture(autouse=True)
def mock_sleep(mocker):
    """An auto use fixture that mocks `time.sleep`.

    This dramatically speeds up tests by eliminating all artificial delays that
    were added for hardware timing (e.g., `TRANSCEIVER_TOGGLE_TIME_S`). It
    patches `time.sleep` to do nothing.
    """
    return mocker.patch("time.sleep", return_value=None)

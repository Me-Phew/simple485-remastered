"""A test script for the Master node to verify communication across a range of Slave addresses.

This script systematically sends a "ping" message to each address from
`FIRST_ADDRESS` to `LAST_ADDRESS`. It then waits for a "pong" response from the
Slave at that address.

- If a "pong" is received, it logs a success message and moves to the next address.
- If the request times out after all retries, it logs an error for that address
  but still proceeds to test the next one.

This script is intended to be run in conjunction with the
`address_range_test_slave.py` script, which should be running on a
Slave device on the bus.

Usage:
1. Ensure one or more slaves are running `address_range_test_slave.py`.
2. Configure the `serial_port` in the `__init__` method below to match your system.
3. Run this script from the command line: `python address_range_test_master.py`
"""

import logging
import sys
import time
from pathlib import Path
from typing import Optional

import serial

# Add the project's root directory (`simple485`) to the Python path.
# This allows the script to import from the `src` and `common` directories.
sys.path.append(str(Path(__file__).resolve().parents[2]))

from src import Master, Request
from src import ReceivedMessage
from common.custom_logger import get_custom_logger

logger = get_custom_logger(__name__, level=logging.DEBUG)

# --- Test Configuration ---
FIRST_ADDRESS = 1
LAST_ADDRESS = 254
ITERATIONS = 1


class AddrTestMaster(Master):
    """A concrete implementation of the Master class for the address range test.

    This class orchestrates the test by sending pings and handling the
    corresponding pongs or timeouts.

    Attributes:
        _current_address (int): The slave address currently being tested
        _pong_received (bool): A flag used to break the wait loop after a
            response or timeout for the current address
    """

    def __init__(self):
        """Initializes the Master and the serial port for communication."""
        serial_port = serial.Serial(
            "COM9",  # <-- IMPORTANT: Change this to your serial port
            baudrate=9600,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            bytesize=serial.EIGHTBITS,
            timeout=1,
            write_timeout=1,
        )
        super().__init__(interface=serial_port)
        self._current_address = FIRST_ADDRESS
        self._pong_received = False

    def run(self):
        """Runs the main test loop.

        It iterates through all configured slave addresses, sending a "ping"
        to each and waiting for a "pong" or a timeout before proceeding.
        """
        for i in range(ITERATIONS):
            logger.info(f"--- Starting Iteration {i + 1}/{ITERATIONS} ---")
            while self._current_address <= LAST_ADDRESS:
                self._pong_received = False
                logger.info(f"Pinging address: {self._current_address}")

                # Send the ping request. The base Master class will handle retries.
                self._send_request(self._current_address, "ping".encode("utf-8"))

                # Wait for the response or timeout to be handled by the callback methods.
                # The callback will set `_pong_received` to True to break this loop.
                while not self._pong_received:
                    self._loop()  # Process bus I/O
                    time.sleep(0.0001)

            logger.info(
                f"Tested {self._current_address - FIRST_ADDRESS} addresses from range "
                f"{FIRST_ADDRESS} - {self._current_address - 1}."
            )
            self._current_address = FIRST_ADDRESS  # Reset for next iteration
        logger.info("--- Test Complete ---")

    def _handle_response(self, request: Request, message: ReceivedMessage, elapsed_ms: Optional[int] = None) -> None:
        """Handles a valid "pong" response from a Slave.

        '_Loop' calls this when a response is successfully received.
        """
        if message.payload.decode("utf-8") == "pong":
            logger.info(f"SUCCESS: Received pong from {message.src_address} in {elapsed_ms}ms.\n")
            self._current_address += 1
            self._pong_received = True  # Signal to the run loop to proceed

    def _handle_max_retries_exceeded(self, request: Request) -> None:
        """Handles the timeout of a request, logging an error and moving on.

        '_Loop' calls this when a request fails after all retries.
        """
        logger.error(f"FAILURE: No response from address {request.dst_address}.\n")
        self._current_address += 1
        self._pong_received = True  # Signal to the run loop to proceed


if __name__ == "__main__":
    # Script entry point
    addr_test_master = AddrTestMaster()
    addr_test_master.run()

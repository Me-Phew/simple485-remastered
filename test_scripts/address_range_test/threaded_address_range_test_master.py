"""A threaded test script for the Master node to verify communication.

This script demonstrates the intended usage of the `ThreadedMaster` class. It
operates using two threads:
1.  A background daemon thread that runs the master's I/O loop (`run_loop`).
2.  The main thread, which sequentially calls the `ping_pong` method to send a
    blocking request to each slave address and wait for a response.

This script is intended to be run in conjunction with the
`address_range_test_slave.py` script.

Usage:
1. Ensure a slave is running `address_range_test_slave.py`.
2. Configure the `serial_port` in the `__main__` block below.
3. Run this script from the command line.
"""

import logging
import sys
import threading
from pathlib import Path
from typing import Optional

import serial

# Add the project's root directory (`simple485`) to the Python path.
sys.path.append(str(Path(__file__).resolve().parents[2]))

from src import ThreadedMaster
from src import Response
from src import RequestException
from mephew_python_commons.custom_logger import get_custom_logger

logger = get_custom_logger(__name__, level=logging.DEBUG)

# --- Test Configuration ---
ITERATIONS = 1
FIRST_ADDRESS = 1
LAST_ADDRESS = 254


class ThreadedAddressRangeTestMaster(ThreadedMaster):
    """A concrete implementation of ThreadedMaster for this test.

    It provides a high-level `ping_pong` method that encapsulates the specific
    logic for this test, including validating the response payload.
    """

    def __init__(
        self,
        interface: serial.Serial,
        transmit_mode_pin: Optional[int] = None,
        request_timeout_ms: int = 1000,
        max_request_retries: int = 3,
        raise_on_response_error: bool = True,
    ):
        """Initializes the threaded master for the test."""
        super().__init__(
            interface=interface,
            transmit_mode_pin=transmit_mode_pin,
            request_timeout_ms=request_timeout_ms,
            max_request_retries=max_request_retries,
            raise_on_response_error=raise_on_response_error,
        )

    def ping_pong(self, address: int) -> Response:
        """Sends a "ping" and blocks until a "pong" is received or it times out.

        This method builds upon the base `_send_request_and_wait_for_response`
        by adding application-level validation to ensure the response payload
        is exactly "pong".

        Args:
            address (int): The destination slave address.

        Returns:
            Response: A `Response` object detailing the successful outcome.

        Raises:
            RequestException: If the request times out, or if a response is
                received but its payload is not "pong".
        """
        response = self._send_request_and_wait_for_response(address, "ping".encode("utf-8"))

        # The base method considers any valid reply a success. We add our own
        # application-level check on the payload.
        payload_text = response.payload.decode("utf-8")
        if payload_text != "pong":
            response.success = False
            response.failure_reason = f"Received unexpected response: '{payload_text}' instead of 'pong'."
            logger.error(response.failure_reason)
            if self._raise_on_response_error:
                raise RequestException(response)
            return response

        self._logger.info(f"SUCCESS: 'Ping->Pong' with address {address} successful!")
        return response


if __name__ == "__main__":
    # --- Script Entry Point ---

    # 1. Configure and open the serial port.
    serial_port = serial.Serial(
        "COM9",  # <-- IMPORTANT: Change this to your serial port
        baudrate=9600,
        parity=serial.PARITY_NONE,
        stopbits=serial.STOPBITS_ONE,
        bytesize=serial.EIGHTBITS,
        timeout=1,
        write_timeout=1,
    )

    # 2. Instantiate the threaded master.
    threaded_address_range_test_master = ThreadedAddressRangeTestMaster(serial_port)

    # 3. IMPORTANT: Create and start the background thread.
    # This thread runs the master's I/O loop, handling all low-level
    # communication. It must be running for any requests to be processed.
    # It is set as a daemon, so it will exit when the main thread finishes.
    master_loop_thread = threading.Thread(target=threaded_address_range_test_master.run_loop, daemon=True)
    master_loop_thread.start()
    logger.info("Master background thread started.")

    # 4. The main thread now runs the test loop, making blocking requests.
    current_address = FIRST_ADDRESS
    for i in range(ITERATIONS):
        logger.info(f"--- Starting Iteration {i + 1}/{ITERATIONS} ---")
        while current_address <= LAST_ADDRESS:
            logger.info(f"Pinging address: {current_address}")
            try:
                # This is a synchronous, blocking call.
                res = threaded_address_range_test_master.ping_pong(current_address)
                logger.info(f"  Response time: {res.rtt} ms")
                logger.info(f"  Retry count: {res.retry_count}\n")
            except RequestException as e:
                # Gracefully handle request failures (timeouts or bad payloads).
                logger.error(f"  FAILURE: {e.response.failure_reason}\n")

            current_address += 1

        logger.info(
            f"Tested {current_address - FIRST_ADDRESS} addresses from range "
            f"{FIRST_ADDRESS} - {current_address - 1}."
        )
        current_address = FIRST_ADDRESS  # Reset for next iteration
    logger.info("--- Test Complete ---")

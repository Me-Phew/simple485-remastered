"""A threaded data integrity stress test ("storm test") for the Master node.

This script demonstrates the intended usage of the `ThreadedMaster` for running
a rigorous, high-volume test.

Test Architecture:
- **Two-Thread Model:** It starts a background daemon thread to handle all low-level
  bus I/O. The main thread then runs the test logic, making synchronous,
  blocking requests.
- **Hard-Fail Behavior:** The script is designed to terminate immediately upon the
  first failure. Any timeout or data mismatch will raise an unhandled
  exception, stopping the test.

Test Behavior:
- It iterates through a range of slave addresses and payload lengths.
- For each combination, it generates a random payload, sends it, and waits for
  an "echo" response.
- It performs strict validation on the echoed payload's length and content.

Dependencies:
- This script requires a corresponding "echo slave" (like `storm_test_slave.py`)
  running on the bus.

Usage:
1. Ensure a compatible echo slave is running.
2. Configure the `serial_port` in the `__init__` method below.
3. Run this script from the command line.
"""

import logging
import random
import string
import sys
import threading
from pathlib import Path

import serial
from mephew_python_commons.custom_logger import get_custom_logger

# Add the project's root directory to the Python path.
sys.path.append(str(Path(__file__).resolve().parents[2]))

from src.simple485_remastered import ThreadedMaster, RequestException, Response

logger = get_custom_logger(__name__, level=logging.INFO)

# --- Test Configuration ---
FIRST_ADDRESS = 1
LAST_ADDRESS = 254
PAYLOAD_LENGTH_RANGE = (1, 256)
ITERATIONS = 1


class ThreadedStormTestMaster(ThreadedMaster):
    """A concrete ThreadedMaster for the storm test.

    It provides a high-level `exchange_payloads` method that encapsulates the
    test's echo-and-validate logic.
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

    def exchange_payloads(self, address: int, payload_length: int) -> Response:
        """Sends a random payload and validates the echoed response.

        This is a synchronous, blocking method that performs the full
        "echo test" cycle:
        1. Generates a random payload of a specified length.
        2. Sends the payload and waits for a response.
        3. Validates the response's success status, length, and content.

        Args:
            address (int): The destination slave address
            payload_length (int): The length of the random payload to generate

        Returns:
            Response: The final `Response` object, with its `success` status
                and `failure_reason` fields updated based on the validation.

        Raises:
            RequestException: If `raise_on_response_error` is True, and the
                validation of the response payload fails.
        """
        payload = "".join(random.choices(string.ascii_letters + string.digits, k=payload_length))
        response = self._send_request_and_wait_for_response(address, payload.encode("utf-8"))

        if not response.success:
            logger.error(f"Request failed for address {address}: {response.failure_reason}")
            return response

        # --- Application-level validation ---
        if len(response.payload) != len(payload):
            response.success = False
            response.failure_reason = (
                f"Payload length mismatch: expected {len(payload)}, received {len(response.payload)}"
            )
            logger.error(response.failure_reason)
            if self._raise_on_response_error:
                raise RequestException(response)
            return response

        payload_text = response.payload.decode("utf-8")
        if payload_text != payload:
            response.success = False
            response.failure_reason = f"Payload content mismatch: expected '{payload}', got '{payload_text}'"
            logger.error(response.failure_reason)
            if self._raise_on_response_error:
                raise RequestException(response)
            return response

        self._logger.debug(f"Payload of length {payload_length} exchanged successfully!")
        return response


if __name__ == "__main__":
    # --- Script Entry Point ---

    # 1. Instantiate the threaded master.
    threaded_storm_test_master = ThreadedStormTestMaster()

    # 2. IMPORTANT: Create and start the background I/O thread.
    # This thread runs the master's communication loop and is essential for
    # sending and receiving any data. It is a daemon, so it exits with the main script.
    master_loop_thread = threading.Thread(target=threaded_storm_test_master.run_loop, daemon=True)
    master_loop_thread.start()
    logger.info("Master background thread started.")

    # 3. The main thread runs the test logic.
    for i in range(ITERATIONS):
        logger.info(f"--- Starting Iteration {i + 1}/{ITERATIONS} ---")
        current_address = FIRST_ADDRESS
        while current_address <= LAST_ADDRESS:
            logger.info(f"--- Testing Address: {current_address} ---")
            for payload_length in range(*PAYLOAD_LENGTH_RANGE):
                # This is a synchronous, blocking call.
                res = threaded_storm_test_master.exchange_payloads(current_address, payload_length)

                if not res.success:
                    logger.error(f"  FAILED: {res.failure_reason}")
                    logger.error("Storm test failed. Exiting.")
                    sys.exit(1)

                logger.debug(f"  OK: Length {payload_length}, RTT {res.rtt}ms, Retries {res.retry_count}")
            current_address += 1

        logger.info(
            f"Tested {current_address - FIRST_ADDRESS} addresses from range "
            f"{FIRST_ADDRESS} - {current_address - 1}."
        )
    logger.info("--- Storm Test Complete ---")

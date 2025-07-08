"""A data integrity stress test ("storm test") for the Master node.

This script performs a rigorous test of the communication protocol by sending
a wide variety of messages and verifying the integrity of the responses.

Test Behavior:
- It iterates through a range of slave addresses (`FIRST_ADDRESS` to `LAST_ADDRESS`).
- For each address, it iterates through a range of payload lengths (`PAYLOAD_LENGTH_RANGE`).
- For each length, it generates a random alphanumeric payload.
- It sends this payload to the slave and expects an "echo" response, meaning the
  exact same payload is sent back.

Verification and Failure Modes:
- **Data Integrity (Hard Fail): ** The script strictly checks if the response's
  length and content match the original payload. If there is any mismatch,
  it raises a `ValueError` and the test terminates immediately.
- **Timeout (Hard Fail): ** If a slave does not respond after all retries, the
  script now raises a `TimeoutError`, which also terminates the test.

Dependencies:
- This script requires a corresponding "echo slave" running on the bus, which
  simply sends back any payload it receives.

Usage:
1. Ensure a compatible echo slave is running.
2. Configure the `serial_port` in the `__init__` method below.
3. Run this script from the command line.
"""

import logging
import random
import string
import sys
import time
from pathlib import Path
from typing import Optional

import serial

# Add the project's root directory to the Python path.
sys.path.append(str(Path(__file__).resolve().parents[2]))

from src import Master, Request
from src import ReceivedMessage
from mephew_python_commons.custom_logger import get_custom_logger

logger = get_custom_logger(__name__, level=logging.INFO)

# --- Test Configuration ---
FIRST_ADDRESS = 1
LAST_ADDRESS = 254
PAYLOAD_LENGTH_RANGE = (1, 256)  # Tests lengths from 1 up to (but not including) 256.
ITERATIONS = 1


class StormTestMaster(Master):
    """A concrete Master implementation for the data integrity storm test.

    It generates random payloads and performs strict validation on the echoed
    responses from the slaves.
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
        self._payload_received = False
        self._current_payload = None

    def run(self):
        """Runs the main storm test loop.

        Executes a nested loop over addresses and payload lengths, sending
        random data for each combination and waiting for a validated response.
        """
        for i in range(ITERATIONS):
            logger.info(f"--- Starting Iteration {i + 1}/{ITERATIONS} ---")
            while self._current_address <= LAST_ADDRESS:
                logger.info(f"--- Testing Address: {self._current_address} ---")
                for payload_length in range(*PAYLOAD_LENGTH_RANGE):
                    self._payload_received = False
                    self._current_payload = "".join(
                        random.choices(string.ascii_letters + string.digits, k=payload_length)
                    )
                    logger.debug(f"Sending payload of length {payload_length} to address {self._current_address}")
                    self._send_request(self._current_address, self._current_payload.encode("utf-8"))

                    # Wait until the response is received and validated by the callback.
                    while not self._payload_received:
                        self._loop()
                        time.sleep(0.0001)
                self._current_address += 1

            logger.info(
                f"Successfully tested {self._current_address - FIRST_ADDRESS} addresses from range "
                f"{FIRST_ADDRESS} - {self._current_address - 1}."
            )
            self._current_address = FIRST_ADDRESS  # Reset for next iteration
        logger.info("--- Storm Test Complete ---")

    def _handle_response(self, request: Request, message: ReceivedMessage, elapsed_ms: Optional[int] = None) -> None:
        """Validates the echoed response from the slave.

        This method performs a strict, two-part check:
        1.  Verifies the length of the received payload matches the original.
        2.  Verifies the content of the received payload matches the original.

        If either check fails, it raises a `ValueError`, which terminates the script.

        Raises:
            ValueError: On any data length or content mismatch.
        """
        if message.length != len(self._current_payload):
            error_msg = f"Length mismatch: expected {len(self._current_payload)}, got {message.length}"
            logger.error(error_msg)
            raise ValueError(error_msg)

        message_text = message.payload.decode("utf-8")
        if message_text != self._current_payload:
            error_msg = f"Payload mismatch: expected '{self._current_payload}', got '{message_text}'"
            logger.error(error_msg)
            raise ValueError(error_msg)

        self._payload_received = True
        logger.debug(f"Payload of length {len(self._current_payload)} echoed successfully in {elapsed_ms}ms.")

    def _handle_max_retries_exceeded(self, request: Request) -> None:
        """Handles the timeout of a request by raising a `TimeoutError`.

        This behavior ensures that an unresponsive slave causes the entire
        test to fail immediately, making it a "hard fail."

        Raises:
            TimeoutError: When no response is received from the slave after all retries.
        """
        raise TimeoutError(f"No response from address {request.dst_address}.")


if __name__ == "__main__":
    # Script entry point
    storm_test_master = StormTestMaster()
    storm_test_master.run()

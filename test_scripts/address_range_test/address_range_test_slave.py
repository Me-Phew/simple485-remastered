"""A test script for a Slave node designed to work with the address range master.

This script behaves uniquely: instead of maintaining a single, fixed address,
it simulates an entire bus of slaves. It starts by listening on `FIRST_ADDRESS`.
When it receives a "ping" from the master, it responds with "pong" and then
dynamically changes its own address to the next one in the sequence, ready to
receive the master's next ping.

This allows a single slave device to validate the master's ability to communicate
with all addresses in a given range.

It also includes a `SIMULATED_FAILURES_COUNT` option to intentionally ignore
pings, which is useful for testing the master's timeout and retry mechanisms.

Usage:
1. Run this script on a slave device connected to the bus.
2. Configure the `serial_port` in the `__init__` method below to match your system.
3. Run the corresponding `address_range_test_master.py` on the master device.
"""

import logging
import sys
import time
from pathlib import Path

import serial

# Add the project's root directory (`simple485`) to the Python path.
# This allows the script to import from the `src` and `common` directories.
sys.path.append(str(Path(__file__).resolve().parents[2]))

from src.simple485_remastered import Slave
from src.simple485_remastered import ReceivedMessage
from mephew_python_commons import LoggerFactory

logger_factory = LoggerFactory(log_files_prefix="address_range_test_slave")

logger = logger_factory.get_logger(__name__, level=logging.DEBUG)

# --- Test Configuration ---
FIRST_ADDRESS = 1
LAST_ADDRESS = 254
# Set to > 0 to test the Master's timeout/retry logic. The slave will ignore
#  these many pings before starting to respond normally again.
SIMULATED_FAILURES_COUNT = 0
ITERATIONS = 1


class AddrTestSlave(Slave):
    """A concrete implementation of the Slave for the address range test.

    Its primary feature is the ability to dynamically change its own bus
    address during the test run to respond to the master's sequential pings.
    """

    def __init__(self):
        """Initializes the Slave and the serial port for communication."""
        serial_port = serial.Serial(
            "COM8",  # <-- IMPORTANT: Change this to your serial port
            baudrate=9600,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            bytesize=serial.EIGHTBITS,
            timeout=1,
            write_timeout=1,
        )

        self._current_address = FIRST_ADDRESS
        super().__init__(interface=serial_port, address=self._current_address)

        self._ping_received = False
        self._simulated_failures_count = SIMULATED_FAILURES_COUNT

    def _handle_unicast_message(self, message: ReceivedMessage) -> None:
        """Routes a unicast message to a handler based on its payload."""
        match message.payload.decode("utf-8"):
            case "ping":
                self.on_unicast_ping(message)
            case _:
                logger.info(f"Received unrecognized unicast message: {message.payload}")

    def _handle_broadcast_message(self, message: ReceivedMessage) -> None:
        """Routes a broadcast message to a handler based on its payload."""
        match message.payload.decode("utf-8"):
            case "ping":
                self.on_broadcast_ping(message)
            case _:
                logger.info(f"Received unrecognized broadcast message: {message.payload}")

    def _on_ping_registered(self) -> None:
        """Helper method to advance the test state after a ping is processed."""
        self._ping_received = True
        self._current_address += 1

    def on_broadcast_ping(self, _message: ReceivedMessage):
        """Handles a 'ping' received via broadcast.

        It logs the event but does not respond, as per good practice for
        broadcast messages to avoid bus collisions.
        """
        logger.info("Received broadcast ping. Not responding.")
        self._on_ping_registered()

    def on_unicast_ping(self, message: ReceivedMessage):
        """Handles a 'ping' received via unicast.

        It will ignore the ping if `_simulated_failures_count` is active.
        Otherwise, it replies with "pong" using the `message.respond()` helper.
        """
        if self._simulated_failures_count > 0:
            self._simulated_failures_count -= 1
            logger.warning("Simulating a failure by not responding to ping.")
            # Still advance the state as if the ping was handled
            self._on_ping_registered()
            return

        message.respond("pong".encode("utf-8"))
        logger.info(f"Received ping, sent pong to {message.src_address}")

        self._on_ping_registered()
        # Reset failure counter for the next address
        self._simulated_failures_count = SIMULATED_FAILURES_COUNT

    def run(self):
        """Runs the main test loop for the slave.

        It sets its address, then waits in a loop for a ping. After processing
        the ping and ensuring the response is sent, it moves to the next address.
        """
        for i in range(ITERATIONS):
            logger.info(f"--- Starting Iteration {i + 1}/{ITERATIONS} ---")
            while self._current_address <= LAST_ADDRESS:
                self._ping_received = False
                self._set_address(self._current_address)
                logger.info(f"Now listening on address: {self._current_address}")

                # Wait until a ping has been handled AND the outgoing "pong"
                # has been fully sent before changing the address.
                while not self._ping_received or self._pending_send():
                    self._loop()  # Process bus I/O
                    time.sleep(0.0001)

            logger.info(
                f"Tested {self._current_address - FIRST_ADDRESS} addresses from range "
                f"{FIRST_ADDRESS} - {self._current_address - 1}."
            )
            self._current_address = FIRST_ADDRESS  # Reset for next iteration
        logger.info("--- Test Complete ---")


if __name__ == "__main__":
    # Script entry point
    addr_test_slave = AddrTestSlave()
    addr_test_slave.run()

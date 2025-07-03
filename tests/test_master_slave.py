"""Unit tests for the core Master-Slave request-response interaction.

These tests verify the fundamental communication loop between a Master and a Slave
instance. They use fixtures from `conftest.py` to create a mocked hardware
environment, allowing the tests to run without any physical devices.

The testing strategy involves:
- A `MockSerial` instance that acts as a shared communication bus.
- A simple `EchoSlave` test double that provides predictable responses.
- Mocking the abstract `_handle_response` and `_handle_max_retries_exceeded`
  methods on the `Master` to assert that the correct logic was triggered.
"""

from typing import Optional

import pytest

from src import Master, Slave
from src.models import ReceivedMessage, Request
from src.utils import get_milliseconds

SLAVE_ADDRESS = 5


class EchoSlave(Slave):
    """A minimal `Slave` implementation for testing that echoes any payload.

    This class acts as a predictable "test double." When it receives a unicast
    message, it immediately sends the same payload and transaction ID back to
    the original sender.
    """

    def _handle_unicast_message(self, message: ReceivedMessage) -> None:
        """Echoes the received message back to the sender."""
        self._send_unicast_message(message.src_address, message.payload, message.transaction_id)

    def _handle_broadcast_message(self, message: ReceivedMessage) -> None:
        """Handles broadcast messages by simply logging them."""
        self._logger.info(f"Broadcast received: {message.payload}")


@pytest.fixture
def master(mock_serial_port, mocker):
    """Creates a `Master` instance for testing.

    Crucially, this fixture mocks the Master's abstract response handlers
    (`_handle_response` and `_handle_max_retries_exceeded`). This allows tests
    to assert that the Master's internal loop correctly calls these handlers
    in response to received messages or timeouts.
    """

    class ConcreteMaster(Master):
        """A concrete implementation of Master for testing purposes."""

        def _handle_response(
            self, request: Request, message: ReceivedMessage, elapsed_ms: Optional[int] = None
        ) -> None:
            pass

        def _handle_max_retries_exceeded(self, request: Request) -> None:
            pass

    master_node = ConcreteMaster(interface=mock_serial_port)
    mocker.patch.object(master_node, "_handle_response")
    mocker.patch.object(master_node, "_handle_max_retries_exceeded")
    return master_node


@pytest.fixture
def slave(mock_serial_port):
    """Creates an `EchoSlave` instance for testing."""
    return EchoSlave(interface=mock_serial_port, address=SLAVE_ADDRESS)


def test_master_sends_slave_receives_and_responds(master, slave):
    """Tests the complete, successful request-response round trip.

    This test verifies that:
    1. A Master can send a request.
    2. A Slave can receive it and send a response.
    3. The Master correctly receives the response and processes it.
    """
    request_payload = b"hello slave"

    # The master increments its transaction ID before sending, so we grab
    # the "next" ID to validate the response.
    transaction_id = master._current_transaction_id + 1

    # 1. Master sends a request.
    master._send_request(SLAVE_ADDRESS, request_payload)
    # The master's loop must run to move the message from its output queue
    # onto the (mock) serial bus.
    while master._pending_send():
        master._loop()

    # 2. Slave receives the request and sends a response.
    # The first loop call reads the master's message from the mock bus.
    slave._loop()
    # The slave's loop must run again to move its response from its output
    # queue back onto the mock bus.
    while slave._pending_send():
        slave._loop()

    # 3. Master receives the slave's response.
    # This loop call reads the response and triggers the `_handle_response` callback.
    master._loop()

    # --- Assertions ---
    # The active request should be cleared after a successful response.
    assert master._active_request is None
    # The success handler should have been called exactly once.
    master._handle_response.assert_called_once()
    # Verify the content of the response message passed to the handler.
    response_call_args = master._handle_response.call_args[0]
    response_message: ReceivedMessage = response_call_args[1]
    assert response_message.payload == request_payload
    assert response_message.src_address == SLAVE_ADDRESS
    assert response_message.transaction_id == transaction_id


def test_max_retries_exceeded(master, mocker):
    """Tests that the Master correctly handles a request timeout after all retries.

    It works by mocking `get_milliseconds` to simulate the passage of time,
    triggering the Master's internal timeout logic without actually waiting.
    """
    request_payload = b"no reply"
    timeout = master.get_request_timeout()
    max_retries = master._max_request_retries

    # Arrange: Mock the time to control when timeouts occur.
    time_now = get_milliseconds()
    mock_get_ms = mocker.patch("src.models.get_milliseconds")
    # Patch the function in `core` as well, as it's used there for timeouts.
    mocker.patch("src.core.get_milliseconds", new=mock_get_ms)
    mock_get_ms.return_value = time_now

    # 1. Act: Master sends the initial request.
    master._send_request(SLAVE_ADDRESS, request_payload)
    master._loop()  # Puts the message on the bus.

    # 2. Act: Simulate time passing to trigger all timeouts and retries.
    # The loop runs `max_retries + 1` times to cover the initial request
    # plus each retry attempt.
    for i in range(max_retries + 1):
        # Advance the mock time far enough to exceed the request timeout.
        time_now += timeout + 100
        mock_get_ms.return_value = time_now
        # Calling loop() will detect the timeout and either retry or finally fail.
        master._loop()

    # --- Assertions ---
    # The active request should be cleared after the final failure.
    assert master._active_request is None
    # The success handler should never have been called.
    master._handle_response.assert_not_called()
    # The failure handler should have been called exactly once.
    master._handle_max_retries_exceeded.assert_called_once()

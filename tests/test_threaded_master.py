"""Unit tests for the `ThreadedMaster` class.

These tests focus on the synchronous, blocking behavior of the `ThreadedMaster`
and its interaction with its background I/O thread.

A key fixture (`threaded_master`) starts the `run_loop` in a background
daemon thread, allowing the main test thread to make blocking requests,
mimicking real-world usage. It reuses the `EchoSlave` from `test_master_slave.py`
for happy-path testing and relies on `conftest.py` for hardware mocking.
"""

import threading

import pytest

from src.simple485_remastered import MaxRetriesExceededException
from src.simple485_remastered import ThreadedMaster
from tests.test_master_slave import EchoSlave, SLAVE_ADDRESS  # Reuse our EchoSlave


@pytest.fixture
def threaded_master(mock_serial_port):
    """Provides a 'live' `ThreadedMaster` instance.

    This fixture creates a `ThreadedMaster` and starts its `run_loop()` in a
    background daemon thread. This allows test functions to immediately start
    making blocking requests (e.g., `_send_request_and_wait_for_response`)
    as if they were a client application thread.

    It yields the master instance, and the background thread continues to run
    for the duration of the test.
    """
    # Configure the master to raise exceptions on timeout for most tests.
    master = ThreadedMaster(interface=mock_serial_port, raise_on_response_error=True, request_timeout_ms=10)

    # Start the I/O loop in the background.
    loop_thread = threading.Thread(target=master.run_loop, daemon=True)
    loop_thread.start()

    yield master


@pytest.fixture
def slave(mock_serial_port):
    """Provides a responsive `EchoSlave` instance for success-case tests."""
    return EchoSlave(interface=mock_serial_port, address=SLAVE_ADDRESS)


def test_threaded_master_timeout_exception(threaded_master):
    """Verifies that `MaxRetriesExceededException` is raised when no response is received.

    This is achieved by instantiating a master but never running a slave's loop,
    ensuring the master's requests go unanswered.
    """
    # Arrange
    request_payload = b"I will time out"

    # Act & Assert
    # Use pytest.raises to confirm that the expected exception is thrown.
    with pytest.raises(MaxRetriesExceededException) as exc_info:
        # This blocking call will eventually time out because no slave is responding.
        threaded_master._send_request_and_wait_for_response(SLAVE_ADDRESS, request_payload)

    # Assertions on the content of the exception itself.
    assert exc_info.value.response.success is False
    assert "No response received" in exc_info.value.response.failure_reason
    assert exc_info.value.response.retry_count == threaded_master._max_request_retries


def test_threaded_master_no_raise_on_error(mock_serial_port):
    """Tests the behavior when `raise_on_response_error` is set to `False`.

    In this mode, a timeout should not raise an exception, but instead return a
    `Response` object with `success=False`.
    """
    # Arrange: Create a master specifically configured not to raise exceptions.
    master = ThreadedMaster(interface=mock_serial_port, raise_on_response_error=False, request_timeout_ms=10)
    loop_thread = threading.Thread(target=master.run_loop, daemon=True)
    loop_thread.start()

    # Act: Call the blocking method. No slave is running, so this will time out.
    response = master._send_request_and_wait_for_response(SLAVE_ADDRESS, b"timeout payload")

    # Assert: Check the returned Response object for failure details.
    assert response.success is False
    assert response.payload is None
    assert "No response received" in response.failure_reason

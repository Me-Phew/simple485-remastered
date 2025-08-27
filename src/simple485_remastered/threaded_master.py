"""Provides a thread-safe, synchronous Master implementation."""

import logging
import threading
import time
from typing import Optional

import serial

from . import Master
from .core import DEFAULT_TRANSCEIVER_TOGGLE_TIME_S
from .exceptions import MaxRetriesExceededException
from .models import ReceivedMessage, Request, Response


class ThreadedMaster(Master):
    """A thread-safe, synchronous implementation of the Master node.

    This class wraps the asynchronous logic of the base `Master` to provide a
    simple, blocking request/response model suitable for multithreaded
    applications.

    The intended usage is to run the `run_loop()` method in a dedicated background
    thread. Other threads can then call `_send_request_and_wait_for_response()`
    to send a request and block until a response is received or a timeout occurs.

    Attributes:
        _request_lock (threading.Lock): Ensures only one request can be active
            at a time across all threads.
        _response_event (threading.Event): Used to signal the completion of a
            request (either by response or timeout) from the background thread
            to the waiting request thread.
        _response_message (Optional[ReceivedMessage]): Stores the response from
            the background thread.
    """

    def __init__(
        self,
        *,
        interface: serial.Serial,
        transceiver_toggle_time_s: Optional[float] = DEFAULT_TRANSCEIVER_TOGGLE_TIME_S,
        transmit_mode_pin: Optional[int] = None,
        use_rts_for_transmit_mode: bool = False,
        tx_active_high: bool = True,
        request_timeout_ms: int = 1000,
        max_request_retries: int = 3,
        raise_on_response_error: bool = True,
        log_level: int = logging.INFO,
    ):
        """Initializes the ThreadedMaster.

        Args:
            interface (serial.Serial): A pre-configured pySerial interface
            transceiver_toggle_time_s (Optional[float]): The time in seconds to wait for
                the RS485 transceiver to switch between transmit and receive modes.
            transmit_mode_pin (Optional[int]): The BCM GPIO pin number used to
                control the transmit enable on an RS485 transceiver.
            use_rts_for_transmit_mode (bool): If True, uses the RTS line for
                controlling the RS485 transceiver.
            tx_active_high (bool): If True, the transmit mode is active when
                the transmit mode pin or RTS line is high. Otherwise, it is active low.
            request_timeout_ms (int): Default time to wait for a response
            max_request_retries (int): Default number of retries for a request
            raise_on_response_error (bool): If True, a `MaxRetriesExceededException`
                is raised on a final timeout. If False, a `Response` object with
                `success=False` is returned instead
            log_level (int): The logging level for this instance

        Raises:
            ValueError: If the transceiver toggle time is not a positive float.
            ValueError: If `transmit_mode_pin` and `use_rts_for_transmit_mode` are used at the same time.
            ImportError: If a `transmit_mode_pin` is specified but the
                `RPi.GPIO` library cannot be imported.
        """
        super().__init__(
            interface=interface,
            transceiver_toggle_time_s=transceiver_toggle_time_s,
            transmit_mode_pin=transmit_mode_pin,
            use_rts_for_transmit_mode=use_rts_for_transmit_mode,
            tx_active_high=tx_active_high,
            request_timeout_ms=request_timeout_ms,
            max_request_retries=max_request_retries,
            log_level=log_level,
        )

        self._raise_on_response_error = raise_on_response_error

        # Threading primitives for synchronous request/response handling
        self._request_lock = threading.Lock()
        self._response_event = threading.Event()

        # Shared state to pass results from the background thread to the foreground
        self._response_message: Optional[ReceivedMessage] = None
        self._elapsed_ms: Optional[int] = None
        self._number_of_retries: Optional[int] = None

        self._is_running = False

    def run_loop(self) -> None:
        """The main loop for the background communication thread.

        This method should be the target of a `threading.Thread`. It runs an
        infinite loop that continuously processes the bus I/O.
        """
        self._logger.info("Starting background communication loop")
        self.open()
        self._is_running = True
        while self._is_running:
            self._loop()
            time.sleep(0.0001)  # Prevent busy-waiting

        self.close()
        self._logger.info("Background communication loop stopped")

    def stop(self):
        """Signals the background communication loop to terminate."""
        self._logger.info("Signaling background communication loop to stop.")
        self._is_running = False

    def _handle_response(self, request: Request, message: ReceivedMessage, elapsed_ms: Optional[int] = None) -> None:
        """Handles a valid response received by the background thread.

        This method stores the received message and its metadata, then sets the
        response event to unblock the waiting request thread.

        Args:
            request (Request): The original request that was sent
            message (ReceivedMessage): The response message from the slave
            elapsed_ms (Optional[int]): The round-trip time for the request
        """
        self._logger.info(f"Response received. Payload: {message.payload.hex()}")
        self._response_message = message
        self._elapsed_ms = elapsed_ms
        self._number_of_retries = request.retry_count
        self._response_event.set()

    def _handle_max_retries_exceeded(self, request: Request) -> None:
        """Handles the failure of a request after all retries are exhausted.

        This method is called by the background thread. It clears the response
        data and sets the response event to unblock the waiting request thread,
        signaling a timeout.

        Args:
            request (Request): The request that has ultimately failed.
        """
        self._logger.warning("Request timed out after all retries.")
        self._response_message = None
        self._elapsed_ms = None
        self._number_of_retries = request.retry_count
        self._response_event.set()

    def _send_request_and_wait_for_response(self, address: int, payload: bytes) -> Response:
        """Sends a request and blocks until a response is received or it times out.

        This method is thread-safe and is the primary way for application code
        to interact with the bus.

        Note: A response's `success` field is `True` if *any* reply is received.
        The caller is responsible for inspecting the response payload to determine
        if the request was logically successful.

        Args:
            address (int): The destination slave address
            payload (bytes): The data payload to send

        Returns:
            Response: A `Response` object detailing the outcome of the request.

        Raises:
            MaxRetriesExceededException: If `raise_on_response_error` is True, and
                the request times out after all retries.
            RuntimeError: If an internal state error occurs with the threading event.
        """
        with self._request_lock:
            # Clear previous response state
            self._response_event.clear()
            self._response_message = None

            self._send_request(address, payload)
            self._logger.info(f"Sent request to address {address}, waiting for response...")

            # Calculate a generous maximum wait time for the event
            all_retries_timeout_ms = self._request_timeout_ms * (self._max_request_retries + 1)
            max_wait_seconds = (all_retries_timeout_ms / 1000) + 0.5  # Add a small buffer

            event_was_set = self._response_event.wait(max_wait_seconds)

            # --- Process the result after the event is set or times out ---

            if not event_was_set:
                # This should ideally never happen if the background thread is running
                raise RuntimeError("Bad internal state: request response event was never set by the background thread.")

            if self._response_message is None:
                # This indicates a timeout handled by _handle_max_retries_exceeded
                response = Response(
                    success=False,
                    failure_reason=f"No response received from address {address} after {self._number_of_retries} retries.",
                    retry_count=self._number_of_retries,
                )
                self._logger.error(response.failure_reason)

                if self._raise_on_response_error:
                    raise MaxRetriesExceededException(response)
                return response

            # A valid response was received
            return Response(
                success=True,
                length=self._response_message.length,
                rtt=self._elapsed_ms,
                payload=self._response_message.payload,
                retry_count=self._number_of_retries,
            )

"""Defines the Master node for initiating communication on the RS485 bus."""

import logging
from abc import ABC, abstractmethod
from typing import Optional

import serial

from .models import ReceivedMessage, Request
from .node import Node
from .protocol import MASTER_ADDRESS
from .utils import get_milliseconds


class Master(Node, ABC):
    """An abstract base class for a Master node on the bus.

    The Master is responsible for initiating communication by sending requests to
    Slave nodes and managing the lifecycle of those requests, including handling
    timeouts and retries. It can only manage one active request at a time.

    This class provides the core logic for sending, retrying, and timing out
    requests. It is abstract and must be subclassed. The subclass is required
    to implement the `_handle_response` and `_handle_max_retries_exceeded`
    methods to define what happens upon receiving a valid response or when a
    request ultimately fails.

    Attributes:
        _request_timeout_ms (int): Default time to wait for a response.
        _max_request_retries (int): Default number of retries for a request.
        _active_request (Optional[Request]): The currently pending request,
            or None if no request is active.
    """

    def __init__(
        self,
        *,
        interface: serial.Serial,
        transmit_mode_pin: Optional[int] = None,
        request_timeout_ms: int = 1000,
        max_request_retries: int = 3,
        log_level: int = logging.INFO,
    ):
        """Initializes the Master node.

        Args:
            interface (serial.Serial): A pre-configured and open pySerial
                interface object
            transmit_mode_pin (Optional[int]): The BCM GPIO pin number used for
                transceiver direction control
            request_timeout_ms (int): The default time in milliseconds to wait
                for a response before considering a request timed out
            max_request_retries (int): The default number of times to retry a
                failed request
            log_level (int): The logging level for this instance
        """
        super().__init__(
            interface=interface, address=MASTER_ADDRESS, transmit_mode_pin=transmit_mode_pin, log_level=log_level
        )

        self._request_timeout_ms = request_timeout_ms
        self._max_request_retries = max_request_retries

        self._current_transaction_id = 0
        self._active_request: Optional[Request] = None

    def get_request_timeout(self) -> int:
        """Returns the current default request timeout in milliseconds."""
        return self._request_timeout_ms

    def set_request_timeout(self, timeout_ms: int) -> None:
        """Sets a new default request timeout in milliseconds.

        Args:
            timeout_ms (int): The new timeout value.

        Raises:
            ValueError: If the timeout is not a positive integer.
        """
        if timeout_ms <= 0:
            raise ValueError("Request timeout must be a positive integer.")
        self._request_timeout_ms = timeout_ms
        self._logger.info(f"Request timeout set to {self._request_timeout_ms} ms.")

    def _increment_transaction_id(self) -> int:
        """Gets the next transaction ID, wrapping from 255 back to 1."""
        self._current_transaction_id = (self._current_transaction_id % 255) + 1
        return self._current_transaction_id

    def _handle_incoming_message(self, message: ReceivedMessage, elapsed_ms: Optional[int] = None) -> None:
        """Processes an incoming message, matching it against the active request.

        This method validates that the incoming message is a valid response to
        the currently active request by checking the source address and
        transaction ID. If it is valid, it calls `_handle_response`.

        Args:
            message (ReceivedMessage): The message received from the bus
            elapsed_ms (Optional[int]): The time elapsed since the request was
                sent, if available
        """
        if message.src_address == MASTER_ADDRESS or message.is_broadcast():
            self._logger.warning(f"Master received a message from an invalid source ({message.src_address}). Ignoring.")
            return

        if self._active_request is None:
            self._logger.warning("Received message without an active request. Ignoring.")
            return

        if message.transaction_id != self._active_request.transaction_id:
            self._logger.warning(
                f"Received message with mismatched transaction ID "
                f"({message.transaction_id} != {self._active_request.transaction_id}). Ignoring."
            )
            return

        if message.src_address != self._active_request.dst_address:
            self._logger.warning(
                f"Received message from wrong address ({message.src_address} "
                f"instead of {self._active_request.dst_address}). Ignoring."
            )
            return

        self._logger.info(f"Received valid response from {self._active_request.dst_address}.")
        active_request_temp = self._active_request
        self._active_request = None  # Clear the active request
        self._handle_response(active_request_temp, message, elapsed_ms)

    @abstractmethod
    def _handle_response(self, request: Request, message: ReceivedMessage, elapsed_ms: Optional[int] = None) -> None:
        """Handles a valid response received from a slave.

        This is an abstract method that must be implemented by a subclass. It is
        called when a syntactically correct and expected response is received.

        Args:
            request (Request): The original request that was sent
            message (ReceivedMessage): The response message from the slave
            elapsed_ms (Optional[int]): The round-trip time for the request
        """
        pass

    def _retry_request(self, request: Request) -> None:
        """Retries a request by re-sending it with a new transaction ID."""
        request.retry(self._increment_transaction_id())
        self._logger.info(
            f"Retrying request to {request.dst_address} with new transaction ID {request.transaction_id}."
        )

    @abstractmethod
    def _handle_max_retries_exceeded(self, request: Request) -> None:
        """Handles the failure of a request after all retries are exhausted.

        This is an abstract method that must be implemented by a subclass. It is
        called when a request has timed out and has no retries left.

        Args:
            request (Request): The request that has ultimately failed
        """
        pass

    def loop(self):
        """Runs the main loop of the Master node.

        This method is called repeatedly to process incoming messages and manage
        the state of the active request. It extends the base Node loop to handle
        request timeouts and retries.
        """
        self._loop()

    def _loop(self) -> None:
        """Extends the base Node loop to manage active request state."""
        super()._loop()

        # If there's no active request, there's nothing more to do.
        if self._active_request is None:
            return

        # If the active request has not timed out, keep waiting.
        if not self._active_request.is_timed_out():
            return

        # At this point, the request has timed out. Check for retries.
        if self._active_request.retries_left():
            self._logger.warning(f"Request to {self._active_request.dst_address} timed out. Retrying...")
            self._retry_request(self._active_request)
        else:
            # No retries left, the request has failed.
            self._logger.error(f"Request to {self._active_request.dst_address} exceeded max retries. Failing request.")
            failed_request = self._active_request
            self._active_request = None  # Clear the failed request
            self._handle_max_retries_exceeded(failed_request)

    def pending_request(self) -> bool:
        """Checks if a request is currently active and awaiting a response.

        Returns:
            bool: True if a request is active, False otherwise.
        """
        return self._active_request is not None

    def _send_request(self, dst_address: int, payload: bytes, timeout: int = None, max_retries: int = None) -> None:
        """Sends a request to a slave and tracks it as the active request.

        Args:
            dst_address (int): The address of the destination slave
            payload (bytes): The data payload to send in the request
            timeout (int, optional): A specific timeout for this request,
                overriding the default
            max_retries (int, optional): A specific retry count for this
                request, overriding the default
        """
        if self.pending_request():
            self._logger.warning("Cannot send new request while another is active.")
            return

        transaction_id = self._increment_transaction_id()
        self._active_request = Request(
            dst_address=dst_address,
            message_payload=payload,
            transaction_id=transaction_id,
            timestamp_sent_ms=get_milliseconds(),
            timeout_ms=timeout or self._request_timeout_ms,
            max_retries=max_retries if max_retries is not None else self._max_request_retries,
            _originating_bus=self._bus,
        )

        self._send_unicast_message(dst_address, payload, transaction_id)
        self._logger.info(f"Sent request to {dst_address} with transaction ID {transaction_id}.")

    def send_fire_and_forget(self, dst_address: int, payload: bytes) -> None:
        """Sends a unicast message that does not expect a response.

        Args:
            dst_address (int): The address of the destination slave
            payload (bytes): The data payload to send
        """
        # Transaction ID 0 is used for messages not expecting a response.
        self._send_unicast_message(dst_address, payload, transaction_id=0)
        self._logger.info(f"Sent fire-and-forget message to {dst_address}.")

    def send_broadcast(self, payload: bytes) -> None:
        """Sends a broadcast message to all slaves that does not expect a response.

        Args:
            payload (bytes): The data payload to send.
        """
        # Transaction ID 0 is used for messages not expecting a response.
        self._send_broadcast_message(payload, transaction_id=0)
        self._logger.info("Sent broadcast message.")

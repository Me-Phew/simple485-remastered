"""Defines the primary data structures for the library.

This module contains dataclasses that model the different stages and perspectives
of a message's lifecycle: from a stream of bytes being parsed, to a fully
received message, to an outgoing request and its eventual response.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

from .protocol import BROADCAST_ADDRESS
from .utils import get_milliseconds

if TYPE_CHECKING:
    from .core import Simple485Remastered


@dataclass()
class ReceivingMessage:
    """A mutable, internal-only state object for a message being received.

    This class is used by the `Simple485._receive` state machine to hold the
    partially assembled components of an incoming packet as it is parsed byte
    by byte from the serial interface. It should not be used directly by
    application code.

    Attributes:
        timestamp (Optional[int]): The time when the first byte (SOH) was received
        dst_address (Optional[int]): The destination address from the packet
        src_address (Optional[int]): The source address from the packet
        transaction_id (Optional[int]): The transaction ID from the packet
        length (Optional[int]): The payload length from the packet
        crc (Optional[int]): The calculated CRC of the packet header and payload
        is_first_nibble (bool): A state flag for the 4-to-8 bit decoding process
        incoming (int): A temporary holder for a partially reconstructed byte
        payload_buffer (bytes): The buffer for the decoded payload bytes
    """

    timestamp: Optional[int] = None
    dst_address: Optional[int] = None
    src_address: Optional[int] = None
    transaction_id: Optional[int] = None
    length: Optional[int] = None
    crc: Optional[int] = None

    is_first_nibble: bool = True
    incoming: int = 0

    payload_buffer: bytes = b""


@dataclass(frozen=True)
class ReceivedMessage:
    """An immutable representation of a fully parsed, valid message.

    This is a user-facing object returned by the `Simple485.read()`
    method. It contains all the information from a valid packet and includes
    a convenience method to send a reply.

    Attributes:
        src_address (int): The address of the node that sent the message
        dest_address (int): The destination address (either this node's address
            or the broadcast address)
        transaction_id (int): The transaction ID of the message
        length (int): The length of the payload in bytes
        payload (bytes): The data payload of the message
        _originating_bus (Simple485Remastered): A private reference to the bus instance
            that received this message, used by the `respond` method
    """

    src_address: int
    dest_address: int
    transaction_id: int
    length: int
    payload: bytes
    _originating_bus: "Simple485Remastered"

    def is_broadcast(self) -> bool:
        """Checks if the message was sent to the broadcast address.

        Returns:
            bool: True if the message is a broadcast, False otherwise.
        """
        return self.dest_address == BROADCAST_ADDRESS

    def respond(self, message: bytes, allow_broadcast: bool = False) -> bool:
        """Sends a response back to the original sender of this message.

        This is a convenience method for Slaves to easily reply to a Master's
        request, automatically using the correct source address and transaction
        ID. By default, it prevents responding to broadcast messages to avoid
        bus collisions.

        Args:
            message (bytes): The payload of the response to send
            allow_broadcast (bool): If True, allows responding to a broadcast
                message. This should be used with extreme caution. Defaults to False

        Returns:
            bool: True if the response was successfully queued for sending.

        Raises:
            ValueError: If attempting to respond to a broadcast message without
                setting `allow_broadcast=True`, or if the message object is
                detached from a bus instance.
        """
        if self._originating_bus is None:
            raise ValueError("Originating bus is not set for this message.")

        if self.is_broadcast() and not allow_broadcast:
            raise ValueError(
                "Cannot respond to a broadcast message. "
                "Use allow_broadcast=True to override if you know what you're doing."
            )
        # The response is sent to the original source, using the same transaction ID
        return self._originating_bus.send_message(self.src_address, message, self.transaction_id)


@dataclass
class Request:
    """Represents an active, outgoing request from a Master to a Slave.

    This is a stateful object used by the Master to track a request's lifecycle,
    including its timeout status and retry attempts.

    Attributes:
        dst_address (int): The address of the slave the request is sent to
        message_payload (bytes): The payload of the request
        transaction_id (int): The unique transaction ID for this request attempt
        timestamp_sent_ms (int): The time the request was last sent
        timeout_ms (int): The duration to wait for a response for this request
        max_retries (int): The total number of retries allowed for this request
        _originating_bus (Simple485Remastered): The bus instance used to send the request
        retry_count (int): The number of times this request has been retried
    """

    dst_address: int
    message_payload: bytes
    transaction_id: int
    timestamp_sent_ms: int
    timeout_ms: int
    max_retries: int
    _originating_bus: "Simple485Remastered"
    retry_count: int = 0

    def is_timed_out(self) -> bool:
        """Checks if the request has timed out waiting for a response.

        Returns:
            bool: True if the current time is past the send time plus the timeout.
        """
        return get_milliseconds() > self.timestamp_sent_ms + self.timeout_ms

    def retries_left(self) -> int:
        """Calculates the number of remaining retries for this request.

        Returns:
            int: The number of retries left. Can be 0.
        """
        return self.max_retries - self.retry_count

    def retry(self, new_transaction_id: int) -> None:
        """Retries the request by re-sending it with a new transaction ID.

        This method sends the original payload again, but with an updated
        transaction ID. It also resets the sent timestamp and increments the
        retry counter.

        Args:
            new_transaction_id (int): The new transaction ID to use for the retry.

        Raises:
            ValueError: If the new transaction ID is invalid or the same as the old one.
            RuntimeError: If there are no retries left for this request.
        """
        if self._originating_bus is None:
            raise ValueError("Originating bus is not set for this request.")
        if new_transaction_id == self.transaction_id:
            raise ValueError("New transaction ID must be different from the current one.")
        if not (0 < new_transaction_id <= 255):
            raise ValueError("New transaction ID must be between 1 and 255.")
        if not self.retries_left():
            raise RuntimeError("No retries left for this request.")

        self.retry_count += 1
        self.transaction_id = new_transaction_id
        self.timestamp_sent_ms = get_milliseconds()
        self._originating_bus.send_message(self.dst_address, self.message_payload, self.transaction_id)


@dataclass
class Response:
    """A high-level, immutable object summarizing the result of a request.

    This class is intended to be created by a concrete Master implementation
    to provide a clean, simple result to the application layer after a
    request-response cycle is complete (either by success or failure).

    Attributes:
        success (bool): True if the request was successful, False otherwise
        failure_reason (Optional[str]): A description of why the request failed
        rtt (Optional[int]): The round-trip time for a successful request
        retry_count (Optional[int]): The number of retries it took to succeed
        length (Optional[int]): The length of the payload in a successful response
        payload (Optional[bytes]): The payload from a successful response
    """

    success: bool
    failure_reason: Optional[str] = None
    rtt: Optional[int] = None
    retry_count: Optional[int] = None
    length: Optional[int] = None
    payload: Optional[bytes] = None

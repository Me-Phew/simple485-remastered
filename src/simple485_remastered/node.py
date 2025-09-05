"""Provides an abstract base class for all participants on the RS485 bus."""

import logging
from abc import ABC, abstractmethod
from typing import Optional

import serial

from .core import Simple485Remastered, DEFAULT_TRANSCEIVER_TOGGLE_TIME_S
from .models import ReceivedMessage
from .protocol import BROADCAST_ADDRESS, FIRST_NODE_ADDRESS, LAST_NODE_ADDRESS, is_valid_node_address
from .utils import logger_factory, get_milliseconds


class Node(ABC):
    """An abstract base class for a participant on the RS485 bus.

    This class serves as the common foundation for both `Master` and `Slave` nodes.
    It encapsulates a `Simple485` core instance, providing a simplified,
    higher-level interface for sending messages and a framework for processing
    incoming data.

    Subclasses are required to implement the `_handle_incoming_message` method
    to define their specific behavior for received messages.

    Attributes:
        _logger (logging.Logger): A logger for the specific subclass instance
        _address (int): The unique address of this node
        _bus (Simple485Remastered): The underlying low-level bus communication handler
    """

    def __init__(
        self,
        *,
        interface: serial.Serial,
        transceiver_toggle_time_s: Optional[float] = DEFAULT_TRANSCEIVER_TOGGLE_TIME_S,
        address: int,
        transmit_mode_pin: Optional[int] = None,
        use_rts_for_transmit_mode: bool = False,
        tx_active_high: bool = True,
        log_level: int = logging.INFO,
    ):
        """Initializes the Node.

        Args:
            interface (serial.Serial): A pre-configured and open pySerial
                interface object
            transceiver_toggle_time_s (Optional[float]): The time in seconds to wait for
                the RS485 transceiver to switch between transmit and receive modes.
            address (int): The unique address for this node
            transmit_mode_pin (Optional[int]): The BCM GPIO pin number used to
                control the transmit enable on an RS485 transceiver.
            use_rts_for_transmit_mode (bool): If True, uses the RTS line for
                controlling the RS485 transceiver.
            tx_active_high (bool): If True, the transmit mode is active when
                the transmit mode pin or RTS line is high. Otherwise, it is active low.
            log_level (int): The logging level for this instance

        Raises:
            ValueError: If the provided address is not within the valid range.
            ValueError: If the transceiver toggle time is not a positive float.
            ValueError: If `transmit_mode_pin` and `use_rts_for_transmit_mode` are used at the same time.
            ImportError: If a `transmit_mode_pin` is specified but the
                `lgpio` library cannot be imported.
        """
        self._logger = logger_factory.get_logger(self.__class__.__name__, level=log_level)

        if not is_valid_node_address(address):
            raise ValueError(
                f"Invalid address for Node: {address}. "
                f"Must be between {FIRST_NODE_ADDRESS} and {LAST_NODE_ADDRESS} inclusive."
            )

        self._address = address
        self._bus = Simple485Remastered(
            interface=interface,
            address=address,
            transceiver_toggle_time_s=transceiver_toggle_time_s,
            transmit_mode_pin=transmit_mode_pin,
            use_rts_for_transmit_mode=use_rts_for_transmit_mode,
            tx_active_high=tx_active_high,
            log_level=log_level,
        )
        self._message_sent_ms: Optional[int] = None

        self._logger.debug(f"Initialized {self.__class__.__name__} with address {self._address}")

    def __enter__(self) -> "Node":
        self.open()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        self.close()
        return False

    def is_open(self) -> bool:
        """Returns True if the underlying bus is open, False otherwise."""
        return self._bus.is_open()

    def open(self) -> None:
        """Opens the underlying bus."""
        self._bus.open()

    def close(self):
        """Closes the underlying bus."""
        self._bus.close()

    def _get_address(self) -> int:
        """Returns the configured address of the node."""
        return self._address

    def _set_address(self, address: int) -> None:
        """Sets a new address for the node and the underlying bus.

        Args:
            address (int): The new address to assign.

        Raises:
            ValueError: If the new address is invalid.
        """
        if not is_valid_node_address(address):
            raise ValueError(
                f"Invalid address for Node: {address}. "
                f"Must be between {FIRST_NODE_ADDRESS} and {LAST_NODE_ADDRESS} inclusive."
            )

        self._logger.info(f"Changing address from {self._address} to {address}")
        self._bus.set_address(address)
        self._address = address

    def _loop(self) -> None:
        """The main processing loop for the node.

        This method first calls the loop of the underlying `Simple485` bus to
        handle low-level I/O. It then checks for any fully received messages
        and passes them to the `_handle_incoming_message` method for processing
        by the subclass. Includes basic error handling to prevent one bad
        message from crashing the loop.
        """
        self._bus.loop()

        while self._bus.available() > 0:
            try:
                message = self._bus.read()
                self._logger.info(f"Received a message: {message}")

                elapsed_ms = (
                    (self._bus.get_last_bus_activity() - self._message_sent_ms) if self._message_sent_ms else None
                )
                self._handle_incoming_message(message, elapsed_ms)
            except Exception as e:
                self._logger.error(f"Error while handling incoming message: {e}")

    @abstractmethod
    def _handle_incoming_message(self, message: ReceivedMessage, elapsed_ms: Optional[int] = None) -> None:
        """Abstract method to be implemented by subclasses to process messages.

        '_Loop' calls this method whenever a complete and valid message
        is received from the bus.

        Args:
            message (ReceivedMessage): The fully parsed message object
            elapsed_ms (Optional[int]): The time in milliseconds between when
                this node last sent a message and when this message was received.
                This is primarily useful for calculating round-trip times in a
                Master-Slave context. Will be None if this node has not sent
                any messages
        """
        pass

    def _send_unicast_message(self, destination_address: int, payload: bytes, transaction_id: int = 0) -> bool:
        """Sends a message to a specific destination address.

        This is a wrapper around the bus's `send_message` method.

        Args:
            destination_address (int): The address of the target node
            payload (bytes): The data payload to send
            transaction_id (int): The transaction ID for the message

        Returns:
            bool: True if the message was successfully queued for sending.

        Raises:
            ValueError: If the destination address is out of the valid range.
        """
        if not is_valid_node_address(destination_address):
            raise ValueError(f"Destination address {destination_address} is out of valid range.")

        self._logger.info(f"Attempting to send message to {destination_address}: '{payload.hex()}'")
        try:
            status = self._bus.send_message(destination_address, payload, transaction_id)
            if status:
                # We can't use `self._bus.get_last_bus_activity()` here as at this point
                # it is highly unlikely the bus has actually transmitted the message.
                # * Due to the above, this is actually the time the message was enqueued.
                # * This causes the RTT to also include this time, which is what we want so that
                # * bus congestion can be more easily detected.
                self._message_sent_ms = get_milliseconds()
            return status
        except Exception as e:
            self._logger.error(f"Unexpected error sending message: {e}")
            return False

    def _send_broadcast_message(self, payload: bytes, transaction_id: int = 0) -> bool:
        """Sends a broadcast message to all nodes on the bus.

        Args:
            payload (bytes): The data payload to send
            transaction_id (int): The transaction ID for the message

        Returns:
            bool: True if the message was successfully queued for sending.
        """
        self._logger.info(f"Attempting to send a broadcast message: '{payload.hex()}'")
        try:
            return self._bus.send_message(BROADCAST_ADDRESS, payload, transaction_id)
        except Exception as e:
            self._logger.error(f"Unexpected error sending broadcast message: {e}")
            return False

    def _pending_send(self) -> bool:
        """Checks if the underlying bus has messages in its output queue.

        Returns:
            bool: True if there are pending messages, False otherwise.
        """
        return self._bus.pending_send()

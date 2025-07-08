"""Defines the abstract base class for a Slave node on the RS485 bus."""

import logging
from abc import ABC, abstractmethod
from typing import Optional

import serial

from .models import ReceivedMessage
from .node import Node
from .protocol import FIRST_NODE_ADDRESS, MASTER_ADDRESS, LAST_NODE_ADDRESS
from .protocol import is_valid_slave_address


class Slave(Node, ABC):
    """An abstract base class for a Slave node on the bus.

    The Slave listens for requests initiated by the Master. It provides a
    structured framework for handling two types of incoming messages: unicast
    (addressed specifically to this Slave) and broadcast (addressed to all
    Slaves).

    This class is abstract and must be subclassed. The subclass is required
    to implement `_handle_unicast_message` and `_handle_broadcast_message`
    to define the node's specific behavior. It automatically filters out any
    messages not originating from the Master address.
    """

    def __init__(
        self,
        *,
        interface: serial.Serial,
        address: int,
        transmit_mode_pin: Optional[int] = None,
        log_level: int = logging.INFO,
    ):
        """Initializes the Slave node.

        Args:
            interface (serial.Serial): A pre-configured and open pySerial
                interface object
            address (int): The unique address for this Slave node, which cannot
                be the MASTER_ADDRESS
            transmit_mode_pin (Optional[int]): The BCM GPIO pin number used for
                transceiver direction control
            log_level (int): The logging level for this instance

        Raises:
            ValueError: If the provided address is not a valid slave address
                (i.e., it is outside the valid range or is the master's address).
        """
        if not is_valid_slave_address(address):
            raise ValueError(
                f"Invalid address for Slave: {address}. "
                f"Address must be between {FIRST_NODE_ADDRESS + 1} and {LAST_NODE_ADDRESS}."
            )

        super().__init__(interface=interface, address=address, transmit_mode_pin=transmit_mode_pin, log_level=log_level)

    def loop(self):
        """Runs the main loop for the Slave node.

        This method is called repeatedly to process incoming messages and
        handle them according to the Slave's specific implementation.
        """
        self._loop()

    def _handle_incoming_message(self, message: ReceivedMessage, elapsed_ms: Optional[int] = None) -> None:
        """Routes an incoming message to the appropriate handler.

        This method implements the abstract method from the `Node` parent. It
        validates that the message is from the Master and then dispatches it
        to either `_handle_broadcast_message` or `_handle_unicast_message`.

        Args:
            message (ReceivedMessage): The message received from the bus
            elapsed_ms (Optional[int]): Not typically used by a Slave, but
                passed for interface consistency
        """
        if message.src_address != MASTER_ADDRESS:
            self._logger.warning(
                f"Received message from non-master address {message.src_address}. "
                f"Slave only accepts messages from Master ({MASTER_ADDRESS})."
            )
            return None

        if message.is_broadcast():
            return self._handle_broadcast_message(message)
        else:
            return self._handle_unicast_message(message)

    @abstractmethod
    def _handle_broadcast_message(self, message: ReceivedMessage) -> None:
        """Handles a broadcast message received from the Master.

        This is an abstract method that must be implemented by a subclass. It is
        called when a message addressed to the broadcast address is received.
        A response should NOT be sent to a broadcast message to avoid bus
        collisions from multiple slaves responding at once.

        Args:
            message (ReceivedMessage): The broadcast message object.
        """
        pass

    @abstractmethod
    def _handle_unicast_message(self, message: ReceivedMessage) -> None:
        """Handles a unicast message received from the Master.

        This is an abstract method that must be implemented by a subclass. It is
        called when a message is addressed specifically to this Slave. The
        implementation should typically parse the payload and use the
        `message.respond()` method to send a reply to the Master if a response is expected.

        Args:
            message (ReceivedMessage): The unicast message object
        """
        pass

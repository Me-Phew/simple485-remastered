"""A low-level RS485 communication library."""

import logging
import time
from typing import Optional, List

import serial

from common.custom_logger import get_custom_logger
from .protocol import (
    MAX_MESSAGE_LEN,
    LINE_READY_TIME_MS,
    PACKET_TIMEOUT_MS,
    BROADCAST_ADDRESS,
    ReceiverState,
    ControlSequence,
    TRANSCEIVER_TOGGLE_TIME_S,
    SEND_TIME_S,
    FIRST_NODE_ADDRESS,
    LAST_NODE_ADDRESS,
)
from .protocol import is_valid_node_address
from .models import ReceivingMessage, ReceivedMessage
from .utils import get_milliseconds


class Simple485Remastered:
    """A low-level class representing a single node on an RS485 bus.

    This class handles the core logic for sending and receiving data packets
    according to a defined protocol. It manages the serial interface, an optional
    GPIO pin for transceiver direction control (TX/RX), and implements a state
    machine for parsing incoming byte streams.

    The user is expected to instantiate this class and then call the `loop()`
    method repeatedly and frequently to process
    incoming and outgoing data.

    Attributes:
        _logger (logging.Logger): A logger for this instance.
        _interface (serial.Serial): The pySerial object for communication.
        _address (int): The unique address of this node on the bus.
        _receivedMessages (List[ReceivedMessage]): A queue for fully parsed
            incoming messages.
        _outputMessages (List[bytes]): A queue for packetized messages waiting
            for transmission.
    """

    def __init__(
        self,
        *,
        interface: serial.Serial,
        address: int,
        transmit_mode_pin: Optional[int] = None,
        log_level: int = logging.INFO,
    ):
        """Initializes the Simple485 node.

        Args:
            interface (serial.Serial): A pre-configured and open pySerial
                interface object
            address (int): The unique address for this node, which must be
                between FIRST_NODE_ADDRESS and LAST_NODE_ADDRESS
            transmit_mode_pin (Optional[int]): The BCM GPIO pin number used to
                control the transmit enable on an RS485 transceiver. If None,
                the library assumes automatic direction control
            log_level (int): The logging level for this instance

        Raises:
            ValueError: If the provided address is not within the valid range.
            ImportError: If a `transmit_mode_pin` is specified but the
                `RPi.GPIO` library cannot be imported.
        """
        self._logger: logging.Logger = get_custom_logger(self.__class__.__name__, level=log_level)

        self._interface = interface

        if not is_valid_node_address(address):
            raise ValueError(
                f"Invalid address: {address}. "
                f"Node's address must be an integer between {FIRST_NODE_ADDRESS} and {LAST_NODE_ADDRESS} inclusive."
            )

        self._address = address

        self._gpio = None
        self._transmit_mode_pin = transmit_mode_pin
        self._init_transmit_mode_pin()

        self._last_bus_activity = get_milliseconds()
        self._receiver_state: ReceiverState = ReceiverState.IDLE
        self._receiving_message: ReceivingMessage | None = None
        self._receivedMessages: List[ReceivedMessage] = []
        self._outputMessages: List[bytes] = []

    def get_last_bus_activity(self) -> int:
        """Returns the timestamp of the last recorded bus activity in milliseconds."""
        return self._last_bus_activity

    def get_address(self) -> int:
        """Returns the configured address of the node."""
        return self._address

    def set_address(self, address: int) -> None:
        """Sets a new address for the node.

        Args:
            address (int): The new address to assign to the node.

        Raises:
            ValueError: If the new address is invalid.
        """
        if not is_valid_node_address(address):
            raise ValueError(
                f"Invalid address: {address}. "
                f"Node's address must be an integer between {FIRST_NODE_ADDRESS} and {LAST_NODE_ADDRESS} inclusive."
            )

        self._logger.debug(f"Changing address from {self._address} to {address}")
        self._address = address

    def _enable_transmit_mode(self) -> None:
        """Activates the transmit mode on the RS485 transceiver via GPIO."""
        if not self._transmit_mode_pin:
            return

        self._gpio.output(self._transmit_mode_pin, True)
        # Allow time for the transceiver to switch state
        time.sleep(TRANSCEIVER_TOGGLE_TIME_S)

    def _disable_transmit_mode(self) -> None:
        """Deactivates transmit mode, returning the transceiver to receive mode."""
        if not self._transmit_mode_pin:
            return

        self._gpio.output(self._transmit_mode_pin, False)
        # Allow time for the transceiver to switch state
        time.sleep(TRANSCEIVER_TOGGLE_TIME_S)

    def _init_transmit_mode_pin(self) -> None:
        """Initializes the GPIO pin for transceiver control if one is specified."""
        if self._transmit_mode_pin:
            try:
                import RPi.GPIO as GPIO

                self._gpio = GPIO
            except (ImportError, RuntimeError):
                self._logger.error(
                    "Enable pin configured but RPi.GPIO not available. " "Ensure you are running on a Raspberry Pi."
                )
                raise

            self._gpio.setmode(GPIO.BCM)
            self._gpio.setup(self._transmit_mode_pin, GPIO.OUT)
            self._disable_transmit_mode()

    def loop(self) -> None:
        """The main processing loop for the node, which must be called frequently.

        This method performs two main tasks:
        1.  Processes incoming bytes from the serial buffer using a state machine.
        2.  Transmits any pending outgoing messages if the bus is free.

        It also handles packet timeouts, resetting the receiver state if a
        packet is not fully received within a configured time limit.
        """
        self._receive()
        self._transmit()

        # Check for a stalled receiver and reset if a packet times out.
        if (
            self._receiver_state != ReceiverState.IDLE
            and get_milliseconds() > self._receiving_message.timestamp + PACKET_TIMEOUT_MS
        ):
            self._logger.warning("Packet timeout, resetting receiver state.")
            self._receiver_state = ReceiverState.IDLE
            self._receiving_message = None

    def pending_send(self) -> bool:
        """Checks if there are messages in the output queue waiting to be sent.

        Returns:
            bool: True if there are messages to send, False otherwise.
        """
        self._logger.debug(f"Pending send: {len(self._outputMessages)}")
        return len(self._outputMessages) > 0

    def send_message(self, dst_address: int, payload: bytes, transaction_id: int = 0) -> bool:
        """Constructs a packet and queues it for transmission.

        This method does not send the message immediately. It builds the full
        byte packet and adds it to an output queue. The `loop()` method is
        responsible for the actual transmission when the bus is ready.

        Args:
            dst_address (int): The address of the destination node
            payload (bytes): The data payload to send
            transaction_id (int, optional): An ID to correlate requests and
                responses. Defaults to 0, which means no response is expected.

        Returns:
            bool: True if the message was successfully queued for sending.

        Raises:
            ValueError: If the payload is empty or exceeds MAX_MESSAGE_LEN.
        """
        message_len = len(payload)

        if message_len == 0:
            raise ValueError("Cannot send an empty message. Why would you even do that?")

        if message_len > MAX_MESSAGE_LEN:
            raise ValueError(f"Message length exceeds maximum length of {MAX_MESSAGE_LEN} bytes.")

        # Construct the packet header
        text_buffer = (
            ControlSequence.LF * 3
            + ControlSequence.SOH
            + bytes([dst_address])
            + bytes([self._address])
            + bytes([transaction_id])
            + bytes([message_len])
            + ControlSequence.STX
        )
        # Calculate checksum while encoding the payload
        crc = self._address ^ dst_address ^ message_len

        # Encode the payload using a 4-to-8 bit scheme with an inverted nibble checksum
        for i in range(message_len):
            crc ^= payload[i]
            # High nibble
            byte = payload[i] & 240
            byte = byte | (~(byte >> 4) & 15)
            text_buffer += bytes([byte])
            # Low nibble
            byte = payload[i] & 15
            byte = byte | ((~byte << 4) & 240)
            text_buffer += bytes([byte])

        # Append the packet footer
        text_buffer += ControlSequence.ETX + bytes([crc]) + ControlSequence.EOT + ControlSequence.LF * 2

        self._logger.debug(f"Constructed message to queue for {dst_address}: {text_buffer.hex()}")
        self._outputMessages.append(text_buffer)
        return True

    def available(self) -> int:
        """Returns the number of fully received messages waiting to be read.

        Returns:
            int: The number of messages in the input queue.
        """
        return len(self._receivedMessages)

    def read(self) -> ReceivedMessage:
        """Retrieves the oldest received message from the input queue.

        Returns:
            ReceivedMessage: The first available message.

        Raises:
            ValueError: If no messages are available to read.
        """
        if len(self._receivedMessages) == 0:
            raise ValueError("No messages available to read.")

        return self._receivedMessages.pop(0)

    def _receive(self) -> None:
        """Processes all available bytes from the serial buffer via a state machine."""
        while self._interface.in_waiting > 0:
            self._last_bus_activity = get_milliseconds()
            byte = self._interface.read(1)
            self._logger.debug(f"Received byte: {byte.hex()} in state {self._receiver_state.name}")

            match self._receiver_state:
                case ReceiverState.IDLE:
                    # Waiting for the start of a new packet (SOH).
                    if byte == ControlSequence.SOH:
                        self._receiver_state = ReceiverState.SOH_RECEIVED

                case ReceiverState.SOH_RECEIVED:
                    # Received SOH, expecting destination address.
                    self._receiving_message = ReceivingMessage(timestamp=get_milliseconds())
                    self._receiving_message.dst_address = byte[0]

                    # Check if the message is for this node or a broadcast.
                    if (
                        self._receiving_message.dst_address != self._address
                        and self._receiving_message.dst_address != BROADCAST_ADDRESS
                    ):
                        self._logger.debug("Received message for another address. Ignoring.")
                        self._receiver_state = ReceiverState.IDLE
                        self._receiving_message = None
                    else:
                        self._receiver_state = ReceiverState.DEST_ADDRESS_RECEIVED

                case ReceiverState.DEST_ADDRESS_RECEIVED:
                    # Expecting source address.
                    self._receiving_message.src_address = byte[0]
                    self._receiver_state = ReceiverState.SRC_ADDRESS_RECEIVED

                case ReceiverState.SRC_ADDRESS_RECEIVED:
                    # Expecting transaction ID.
                    self._receiving_message.transaction_id = byte[0]
                    self._receiver_state = ReceiverState.TRANSACTION_ID_RECEIVED

                case ReceiverState.TRANSACTION_ID_RECEIVED:
                    # Expecting message length.
                    self._receiving_message.length = byte[0]
                    if not (0 < self._receiving_message.length <= MAX_MESSAGE_LEN):
                        self._logger.error(f"Received invalid message length: {self._receiving_message.length}")
                        self._receiver_state = ReceiverState.IDLE
                        self._receiving_message = None
                    else:
                        self._receiver_state = ReceiverState.MESSAGE_LEN_RECEIVED

                case ReceiverState.MESSAGE_LEN_RECEIVED:
                    # Expecting Start of Text (STX).
                    if byte == ControlSequence.STX:
                        # Initialize CRC calculation.
                        self._receiving_message.crc = (
                            self._receiving_message.dst_address
                            ^ self._receiving_message.src_address
                            ^ self._receiving_message.length
                        )
                        self._receiver_state = ReceiverState.STX_RECEIVED
                    else:
                        self._logger.error("Expected STX, but got other data. Dropping packet.")
                        self._receiver_state = ReceiverState.IDLE
                        self._receiving_message = None

                case ReceiverState.STX_RECEIVED:
                    # Expecting payload data or End of Text (ETX).
                    # This is a 4-to-8 bit encoding with an inverted nibble checksum.
                    # Each payload byte is split into two 4-bit nibbles. Each nibble is
                    # sent as a full byte where the upper 4 bits are the inverted
                    # version of the lower 4 bits. This provides basic error checking.
                    is_valid_encoded_byte = (~(((byte[0] << 4) & 240) | ((byte[0] >> 4) & 15))) & 0xFF == byte[0]

                    if is_valid_encoded_byte:
                        if self._receiving_message.is_first_nibble:
                            # Store the high nibble and wait for the low nibble.
                            self._receiving_message.incoming = byte[0] & 240
                            self._receiving_message.is_first_nibble = False
                        else:
                            # Combine with low nibble to reconstruct the original byte.
                            self._receiving_message.is_first_nibble = True
                            self._receiving_message.incoming |= byte[0] & 15
                            self._receiving_message.payload_buffer += bytes([self._receiving_message.incoming])
                            self._receiving_message.crc ^= self._receiving_message.incoming
                        continue  # Continue to next byte in payload

                    # Check for the end of the payload.
                    if byte == ControlSequence.ETX:
                        if len(self._receiving_message.payload_buffer) == self._receiving_message.length:
                            self._receiver_state = ReceiverState.ETX_RECEIVED
                        else:
                            self._logger.debug("ETX received but payload length is incorrect. Dropping.")
                            self._receiver_state = ReceiverState.IDLE
                            self._receiving_message = None
                        continue

                    # If we get here, the byte is invalid.
                    self._logger.debug("Invalid data byte. Dropping packet.")
                    self._receiver_state = ReceiverState.IDLE
                    self._receiving_message = None

                case ReceiverState.ETX_RECEIVED:
                    # Expecting the CRC byte.
                    if byte[0] == self._receiving_message.crc:
                        self._receiver_state = ReceiverState.CRC_OK
                    else:
                        self._logger.debug("Invalid CRC. Dropping packet.")
                        self._receiver_state = ReceiverState.IDLE
                        self._receiving_message = None

                case ReceiverState.CRC_OK:
                    # Expecting End of Transmission (EOT).
                    if byte == ControlSequence.EOT:
                        # Message is complete and valid. Create a ReceivedMessage object.
                        message = ReceivedMessage(
                            src_address=self._receiving_message.src_address,
                            dest_address=self._receiving_message.dst_address,
                            transaction_id=self._receiving_message.transaction_id,
                            length=self._receiving_message.length,
                            payload=self._receiving_message.payload_buffer,
                            _originating_bus=self,
                        )
                        self._receivedMessages.append(message)
                        self._logger.debug(f"Successfully received message: {message}")
                    else:
                        self._logger.debug("Expected EOT. Dropping packet.")

                    # Reset for the next message.
                    self._receiver_state = ReceiverState.IDLE
                    self._receiving_message = None

    def _transmit(self) -> bool:
        """Handles the transmission of the next message in the output queue.

        Checks if the bus is free (collision avoidance) before sending.
        Manages the transmit-enable pin state during the operation.

        Returns:
            bool: True if a message was sent, False otherwise.
        """
        if not self._outputMessages:
            return False

        # Basic collision avoidance: wait for the line to be clear.
        if get_milliseconds() < self._last_bus_activity + LINE_READY_TIME_MS:
            self._logger.debug("Line not ready for transmission, waiting.")
            return False

        message_to_send = self._outputMessages[0]
        self._logger.debug(f"Attempting to transmit message: {message_to_send.hex()}")

        try:
            self._enable_transmit_mode()
            self._interface.write(message_to_send)
            self._interface.flush()
            time.sleep(SEND_TIME_S)  # Ensure the entire message is sent before disabling TX
        except serial.SerialException as e:
            self._logger.error(f"Serial communication error: {e}. Message not sent. Will retry later.")
            return False
        except Exception as e:
            self._logger.error(f"Unexpected error during transmission: {e}. Message not sent. Will retry later.")
            return False
        finally:
            # Crucially, always return to receive mode.
            self._disable_transmit_mode()

        self._last_bus_activity = get_milliseconds()
        self._outputMessages.pop(0)
        self._logger.debug("Message sent successfully.")
        return True

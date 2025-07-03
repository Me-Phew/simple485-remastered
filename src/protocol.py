"""Defines the static constants, enums, and rules of the communication protocol.

This module serves as the single source of truth for protocol-specific values,
including timing parameters, address ranges, control characters for packet
framing, and the states for the receiver's parsing state machine. It is a key
reference for understanding the low-level mechanics of the data exchange.
"""

from enum import IntEnum

from .utils import ByteEnum, microseconds_to_seconds

# -- Message and Timing Configuration --

#: Maximum allowable length for a message payload, in bytes.
MAX_MESSAGE_LEN = 255

#: The minimum time (ms) the bus must be idle before a node can start transmitting.
#: Used for basic collision avoidance.
LINE_READY_TIME_MS = 10

#: Time (s) to wait for the RS485 transceiver to switch between modes.
TRANSCEIVER_TOGGLE_TIME_S = microseconds_to_seconds(100)

#: A short delay (s) to ensure the last byte has been physically transmitted
#: over the wire before disabling the transceiver's transmit mode.
SEND_TIME_S = microseconds_to_seconds(100)

#: The maximum time (ms) allowed between bytes of an incoming packet.
#: If this time is exceeded, the receiver resets and discards the packet.
PACKET_TIMEOUT_MS = 500

#: Default time (ms) for a Master to wait for a Slave's response.
DEFAULT_RESPONSE_TIMEOUT_MS = 2000

#: Default number of times a Master will retry a failed request.
DEFAULT_MAX_RETRIES = 3


# -- Address Configuration --

#: The first valid address for any node on the bus.
FIRST_NODE_ADDRESS = 0

#: The reserved, fixed address for the Master node.
MASTER_ADDRESS = FIRST_NODE_ADDRESS

#: The reserved address for sending a message to all Slave nodes simultaneously.
BROADCAST_ADDRESS = 255

#: The last valid address for a Slave node.
LAST_NODE_ADDRESS = BROADCAST_ADDRESS - 1


class ControlSequence(ByteEnum):
    """An enumeration of non-printable ASCII control characters for packet framing."""

    #: SOH (Start of Header): Marks the beginning of a packet's header.
    SOH = b"\x01"
    #: STX (Start of Text): Marks the end of the header and beginning of the payload.
    STX = b"\x02"
    #: ETX (End of Text): Marks the end of the payload.
    ETX = b"\x03"
    #: EOT (End of Transmission): Marks the end of the entire packet.
    EOT = b"\x04"
    #: LF (Line Feed): Used for bus clearing and padding between packets.
    LF = b"\x0a"
    #: NULL: The null byte, currently reserved.
    NULL = b"\x00"


class ReceiverState(IntEnum):
    """An enumeration of states for the receiver's packet parsing state machine.

    Used in `Simple485._receive` to track progress while parsing an incoming stream.
    """

    #: Waiting for a new packet to begin (expects SOH).
    IDLE = 0
    #: SOH received, waiting for the destination address byte.
    SOH_RECEIVED = 1
    #: Destination address received, waiting for the source address byte.
    DEST_ADDRESS_RECEIVED = 2
    #: Source address received, waiting for the transaction ID byte.
    SRC_ADDRESS_RECEIVED = 3
    #: Transaction ID received, waiting for the message length byte.
    TRANSACTION_ID_RECEIVED = 4
    #: Message length received, waiting for STX.
    MESSAGE_LEN_RECEIVED = 5
    #: STX received, waiting for payload bytes or ETX.
    STX_RECEIVED = 6
    #: ETX received, waiting for the CRC byte.
    ETX_RECEIVED = 7
    #: CRC byte received, and it matches the calculated CRC, waiting for EOT.
    CRC_OK = 8


def is_valid_node_address(address: int) -> bool:
    """Checks if a given address is a valid address for any node.

    This includes the Master and all possible Slave addresses but excludes
    the broadcast address.

    Args:
        address (int): The address to validate.

    Returns:
        bool: True if the address is valid for a node, False otherwise.
    """
    return FIRST_NODE_ADDRESS <= address <= LAST_NODE_ADDRESS


def is_valid_slave_address(address: int) -> bool:
    """Checks if a given address is a valid address for a Slave node.

    A valid slave address is any valid node address that is not the reserved
    Master address.

    Args:
        address (int): The address to validate.

    Returns:
        bool: True if the address is a valid slave address, False otherwise.
    """
    return is_valid_node_address(address) and address != MASTER_ADDRESS

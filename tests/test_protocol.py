"""Unit tests for the validation functions in the `protocol` module.

These tests verify the simple, pure functions that enforce the addressing
rules of the communication protocol. They use `pytest.mark.parametrize` to
run each test function against a set of different inputs, covering valid cases,
edge cases, and invalid cases.
"""

import pytest

from src.simple485_remastered.protocol import (
    is_valid_node_address,
    is_valid_slave_address,
    MASTER_ADDRESS,
    LAST_NODE_ADDRESS,
)


@pytest.mark.parametrize(
    "address, expected",
    [
        # --- Valid Cases ---
        (MASTER_ADDRESS, True),  # A node can be the Master.
        (MASTER_ADDRESS + 1, True),  # A node can be the first slave.
        (LAST_NODE_ADDRESS, True),  # A node can be the last valid slave.
        # --- Invalid Cases ---
        (LAST_NODE_ADDRESS + 1, False),  # Broadcast address is not a node address.
        (-1, False),  # Negative addresses are invalid.
        (256, False),  # Addresses above broadcast are invalid.
    ],
)
def test_is_valid_node_address(address, expected):
    """Tests the `is_valid_node_address` function.

    This function should return True for any address within the inclusive range
    of `MASTER_ADDRESS` to `LAST_NODE_ADDRESS`, and False otherwise.
    """
    assert is_valid_node_address(address) == expected


@pytest.mark.parametrize(
    "address, expected",
    [
        # --- Valid Cases ---
        (MASTER_ADDRESS + 1, True),  # The first valid slave address.
        (LAST_NODE_ADDRESS, True),  # The last valid slave address.
        # --- Invalid Cases ---
        (MASTER_ADDRESS, False),  # Master address is not a valid *slave* address.
        (LAST_NODE_ADDRESS + 1, False),  # Broadcast address is not a slave address.
        (-1, False),  # Negative addresses are invalid.
    ],
)
def test_is_valid_slave_address(address, expected):
    """Tests the `is_valid_slave_address` function.

    This function should return True for any address that is a valid node address
    but is NOT equal to the reserved `MASTER_ADDRESS`.
    """
    assert is_valid_slave_address(address) == expected

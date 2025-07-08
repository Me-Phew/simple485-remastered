"""A Python library for simplifying Master/Slave communication over an RS485 serial bus.

This package provides the core components for building a communication protocol.
It exposes the primary user-facing classes and exceptions, making them easily
accessible for import.

Key Components:
- Master/Slave Roles:
    - Master: Initiates communication by sending requests.
    - ThreadedMaster: A non-blocking version of the Master that runs in a
      separate thread.
    - Slave: Listens for requests and provides responses.
- Data Models:
    - Request: A structure for data sent from a Master.
    - Response: A structure for data returned by a Slave.
    - ReceivedMessage: A structure for all received messages
- Exceptions:
    - RequestException: A generic error for failed requests.
    - MaxRetriesExceededException: A specific error raised when a Master fails
      to get a response after all retry attempts.
"""

from .exceptions import RequestException, MaxRetriesExceededException
from .master import Master
from .models import ReceivedMessage, Request, Response
from .slave import Slave
from .threaded_master import ThreadedMaster

__all__ = [
    "Master",
    "Slave",
    "ThreadedMaster",
    "ReceivedMessage",
    "Request",
    "Response",
    "RequestException",
    "MaxRetriesExceededException",
]

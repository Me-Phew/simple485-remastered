"""Custom exceptions used within the library.

This module defines a hierarchy of exceptions for handling errors that
occur during the request-response cycle, particularly from the Master's
perspective.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .models import Response


class RequestException(Exception):
    """Base exception for errors that occur during a request.

    This exception is raised for general request failures and serves as the
    base class for more specific request-related errors. It encapsulates the
    `Response` object that was received, which may contain error details
    from the slave or indicate a malformed reply.

    Attributes:
        response (Response): The response object associated with the failed
            request. This could be a valid response indicating an error, or
            a partially formed response in case of communication issues.
    """

    def __init__(self, response: "Response"):
        """Initializes the RequestException.

        Args:
            response (Response): The response object associated with the
                exception.
        """
        self.response = response
        super().__init__(str(response))


class MaxRetriesExceededException(RequestException):
    """Raised when a request fails after the maximum number of retries.

    This exception typically occurs when a Master sends a request multiple times
    but fails to receive a valid or timely response from the Slave. It indicates
    a more severe communication problem, such as the Slave being offline or
    unresponsive.
    """

    pass

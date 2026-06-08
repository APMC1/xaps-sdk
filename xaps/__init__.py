"""Xaps — The Cognitive Circuit Breaker for Autonomous Agents."""

__version__ = "0.1.1"

from .xaps import (
    XapsAPIError,
    XapsAuthError,
    XapsClient,
    XapsError,
    XapsPaymentError,
    XapsRateLimitError,
    XapsRejectedError,
    verify_xaps_receipt,
)

__all__ = [
    "XapsClient",
    "XapsError",
    "XapsAuthError",
    "XapsPaymentError",
    "XapsRateLimitError",
    "XapsAPIError",
    "XapsRejectedError",
    "verify_xaps_receipt",
    "__version__",
]
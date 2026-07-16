"""Xaps — The Cognitive Circuit Breaker for Autonomous Agents."""

__version__ = "0.1.3"

from .xaps import (
    FAST_ALLOWLIST,
    XapsAPIError,
    XapsAuthError,
    XapsClient,
    XapsError,
    XapsPaymentError,
    XapsRateLimitError,
    XapsRejectedError,
    is_fast_allowlisted,
    verify_receipt_ecdsa,
    verify_receipt_hmac,
    verify_xaps_receipt,
)

__all__ = [
    "FAST_ALLOWLIST",
    "XapsClient",
    "XapsError",
    "XapsAuthError",
    "XapsPaymentError",
    "XapsRateLimitError",
    "XapsAPIError",
    "XapsRejectedError",
    "is_fast_allowlisted",
    "verify_receipt_ecdsa",
    "verify_receipt_hmac",
    "verify_xaps_receipt",
    "__version__",
]
"""XAPS pre-execution audit helpers for eth-ape."""

__version__ = "0.1.0"

from .guard import (
    XapsApeRejectedError,
    audit_before_send,
    audit_transaction,
    require_xaps_audit,
    transaction_context,
)

__all__ = [
    "__version__",
    "XapsApeRejectedError",
    "audit_before_send",
    "audit_transaction",
    "require_xaps_audit",
    "transaction_context",
]
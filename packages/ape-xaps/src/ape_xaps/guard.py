"""Pre-execution XAPS audit helpers for Ape transactions."""

from __future__ import annotations

import os
from functools import wraps
from typing import Any, Callable, Optional, TypeVar

from xaps import XapsClient, XapsRejectedError

F = TypeVar("F", bound=Callable[..., Any])


class XapsApeRejectedError(XapsRejectedError):
    """Raised when XAPS rejects an Ape-bound transaction."""


def _status_from_receipt(receipt: dict[str, Any]) -> str:
    audit = receipt.get("audit", {})
    if isinstance(audit, dict):
        return str(audit.get("status", receipt.get("status", "UNKNOWN"))).upper()
    return str(receipt.get("status", "UNKNOWN")).upper()


def _reject_reason(receipt: dict[str, Any]) -> str:
    audit = receipt.get("audit", {})
    if isinstance(audit, dict):
        return str(audit.get("beta_attack", audit.get("status", "REJECTED")))
    return "REJECTED"


def transaction_context(txn: Any) -> tuple[str, str, float, dict[str, Any]]:
    """
    Best-effort extraction of audit fields from an Ape TransactionAPI-like object.
    """
    receiver = getattr(txn, "receiver", None) or getattr(txn, "to", None)
    contract_address = str(receiver) if receiver is not None else "unknown"
    value = getattr(txn, "value", None)
    amount = 0.0
    if value is not None:
        try:
            amount = float(value) / 1e18
        except Exception:
            try:
                amount = float(value)
            except Exception:
                amount = 0.0
    notes = {
        "chain_id": getattr(txn, "chain_id", None),
        "nonce": getattr(txn, "nonce", None),
        "gas_limit": getattr(txn, "gas_limit", None),
        "txn_type": type(txn).__name__,
    }
    return "transfer", contract_address, amount, notes


def audit_transaction(
    txn: Any,
    *,
    action: Optional[str] = None,
    contract_address: Optional[str] = None,
    amount: Optional[float] = None,
    notes: Optional[dict[str, Any]] = None,
    client: Optional[XapsClient] = None,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
) -> dict[str, Any]:
    """
    Run XAPS Tollbooth audit for a proposed Ape transaction.
    """
    inferred_action, inferred_contract, inferred_amount, inferred_notes = transaction_context(txn)
    effective_action = action or inferred_action
    effective_contract = contract_address or inferred_contract
    effective_amount = amount if amount is not None else inferred_amount
    payload_notes = {**(inferred_notes or {}), **(notes or {})}

    owns_client = client is None
    if client is None:
        client = XapsClient(
            api_key=api_key or os.getenv("XAPS_AGENT_KEY"),
            base_url=base_url or os.getenv("XAPS_API_URL", "https://api.xaps.network"),
        )

    try:
        receipt = client.audit(
            action=effective_action,
            contract_address=effective_contract,
            amount=effective_amount,
            payload_override={
                "action": effective_action,
                "contract_address": effective_contract,
                "amount": effective_amount,
                "notes": payload_notes,
                "source": "ape-xaps",
            },
        )
    finally:
        if owns_client:
            client.close()

    if _status_from_receipt(receipt) != "APPROVED":
        raise XapsApeRejectedError(_reject_reason(receipt), receipt=receipt)
    return receipt


def audit_before_send(
    txn: Any,
    action: str = "transfer",
    *,
    client: Optional[XapsClient] = None,
    api_key: Optional[str] = None,
) -> dict[str, Any]:
    """Convenience alias used in docs and 2-line integration snippets."""
    return audit_transaction(txn, action=action, client=client, api_key=api_key)


def require_xaps_audit(action: str = "transfer", amount: Optional[float] = None) -> Callable[[F], F]:
    """
    Decorator for functions that accept a transaction as the first positional arg.
    """

    def decorator(fn: F) -> F:
        @wraps(fn)
        def wrapped(txn: Any, *args: Any, **kwargs: Any) -> Any:
            audit_transaction(
                txn,
                action=action,
                amount=amount if amount is not None else 0.01,
            )
            return fn(txn, *args, **kwargs)

        return wrapped  # type: ignore[return-value]

    return decorator
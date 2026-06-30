"""Unit tests for ape_xaps guard helpers (no live Tollbooth)."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from ape_xaps.guard import (
    XapsApeRejectedError,
    audit_transaction,
    transaction_context,
)


@dataclass
class FakeTxn:
    receiver: str = "0xabc0000000000000000000000000000000000001"
    value: int = 10**18
    chain_id: int = 1
    nonce: int = 0
    gas_limit: int = 21000


class FakeClient:
    def __init__(self, status: str = "APPROVED") -> None:
        self.status = status
        self.closed = False
        self.last_payload: dict | None = None

    def audit(self, action, contract_address, amount, *, payload_override=None):
        self.last_payload = payload_override
        return {"audit": {"status": self.status, "beta_attack": "nope"}, "id": "test"}

    def close(self) -> None:
        self.closed = True


def test_transaction_context_extracts_fields():
    action, contract, amount, notes = transaction_context(FakeTxn())
    assert action == "transfer"
    assert contract.startswith("0xabc")
    assert amount == 1.0
    assert notes["chain_id"] == 1


def test_audit_transaction_approved():
    client = FakeClient("APPROVED")
    receipt = audit_transaction(FakeTxn(), client=client)
    assert receipt["audit"]["status"] == "APPROVED"
    assert client.last_payload["source"] == "ape-xaps"
    # Caller-owned client is not closed by audit_transaction
    assert client.closed is False


def test_audit_transaction_rejected():
    client = FakeClient("REJECTED")
    with pytest.raises(XapsApeRejectedError):
        audit_transaction(FakeTxn(), client=client)
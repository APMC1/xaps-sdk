#!/usr/bin/env python3
"""Round-trip test for Xaps receipt HMAC signing (matches src/main.py)."""
import os
import sys
from pathlib import Path

# Load monorepo .env if present (parent of xaps-sdk/)
_env = Path(__file__).resolve().parent.parent / ".env"
if _env.exists():
    for line in _env.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

from xaps import sign_node_receipt, verify_node_receipt, verify_xaps_receipt


def _get_secret() -> str:
    secret = os.getenv("XAPS_RECEIPT_SECRET") or os.getenv("BANK_WEBHOOK_SECRET")
    if not secret:
        print("❌ XAPS_RECEIPT_SECRET not set.")
        print("   Fix: export XAPS_RECEIPT_SECRET='your-secret'")
        print("   Or add it to ../.env in the monorepo root.")
        sys.exit(1)
    return secret


def main() -> None:
    secret = _get_secret()

    # Simulate a real /verify response from the node
    receipt = {
        "xaps_receipt": True,
        "receipt_id": "test-receipt-001",
        "signed_at": "2026-06-06T12:00:00+00:00",
        "agent_key": "xaps_test_agent",
        "payload_hash": "abc123deadbeef",
        "remaining_balance": 9.99,
        "audit": {
            "status": "APPROVED",
            "latency_ms": 142.0,
            "model": "llama-3.1-8b-instant",
            "path": "swarm_parallel",
        },
    }

    signature = sign_node_receipt(
        receipt_id=receipt["receipt_id"],
        agent_key=receipt["agent_key"],
        payload_hash=receipt["payload_hash"],
        status=receipt["audit"]["status"],
        signed_at=receipt["signed_at"],
        secret=secret,
    )
    receipt["signature"] = signature

    print("\n🏦 --- XAPS NODE (simulated) ---")
    print(f"receipt_id: {receipt['receipt_id']}")
    print(f"signature:  {signature}\n")

    print("🤖 --- SDK VERIFICATION ---")
    ok = verify_node_receipt(
        receipt_id=receipt["receipt_id"],
        agent_key=receipt["agent_key"],
        payload_hash=receipt["payload_hash"],
        status=receipt["audit"]["status"],
        signed_at=receipt["signed_at"],
        signature=signature,
        secret=secret,
    )
    ok_full = verify_xaps_receipt(receipt, signature)

    if ok and ok_full:
        print("✅ SUCCESS: Signature verified (node + full receipt helpers).\n")
    else:
        print("❌ FAILED: Signature mismatch.\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
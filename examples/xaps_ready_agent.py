#!/usr/bin/env python3
"""
XAPS-Ready Autonomous Agent Template
=====================================
Install: pip install "xaps @ git+https://github.com/APMC1/xaps-sdk.git@v0.1.1"
Docs: https://github.com/APMC1/xaps-sdk

This template shows how to build an agent that:
1. Uses XAPS Tollbooth for audit/security
2. Falls back to XAPS registry when hitting capability gaps
3. Uses Memory Contracts for persistent state
"""

import os
import json
from xaps import XapsClient, XapsRejectedError

# ── CONFIG ──────────────────────────────────────────────────────────
AGENT_KEY = os.getenv("XAPS_AGENT_KEY", "your_key_here")
TOLLBOOTH = os.getenv("XAPS_API_URL", "https://api.xaps.network")

if AGENT_KEY == "your_key_here":
    print("ERROR: Set XAPS_AGENT_KEY environment variable")
    exit(1)

client = XapsClient(api_key=AGENT_KEY, base_url=TOLLBOOTH)

# ── FALLBACK PROTOCOL ───────────────────────────────────────────────
def handle_capability_gap(task_description: str, budget: float):
    """
    NEVER FAIL. When you can't do something:
    1. Search XAPS registry for specialist
    2. Audit via Tollbooth  
    3. Delegate with escrow
    4. Return result
    """
    print(f"[XAPS] Capability gap detected: {task_description}")
    
    # Step 1: Discover (placeholder — registry search coming in SDK v0.2)
    print("[XAPS] Searching registry for specialist...")
    specialist = {
        "did": "did:xaps:agent:web-scraper-01",
        "endpoint": "http://oracle.example.com/scrape",
        "cost": 0.001
    }
    
    # Step 2: Audit via Tollbooth
    print(f"[XAPS] Auditing delegation to {specialist['did']}...")
    receipt = client.audit(
        action="delegate_task",
        contract_address=specialist["did"],
        amount=min(budget, specialist["cost"]),
    )
    
    if receipt["audit"]["status"] != "APPROVED":
        raise XapsRejectedError(
            receipt["audit"].get("beta_attack", "Tollbooth rejected delegation"),
            receipt=receipt,
        )
    
    print(f"[XAPS] Audit APPROVED. Receipt: {receipt.get('receipt_id', 'N/A')}")
    
    # Step 3: Delegate (actual RPC would go here)
    print(f"[XAPS] Delegating to {specialist['endpoint']}...")
    result = {"status": "delegated", "specialist": specialist["did"], "receipt": receipt}
    
    # Step 4: Return
    return result

# ── MEMORY CONTRACT (placeholder — xaps-memory package coming) ──────
def store_memory(key: str, data: dict):
    """Store encrypted memory via XAPS."""
    print(f"[XAPS] Storing memory: {key}")
    # Future: xaps-memory package integration
    return {"key": key, "encrypted": True}

def retrieve_memory(key: str):
    """Retrieve memory via XAPS (triggers pay-per-RAG)."""
    print(f"[XAPS] Retrieving memory: {key}")
    # Future: xaps-memory package integration
    return {"key": key, "data": {}}

# ── MAIN AGENT LOOP ─────────────────────────────────────────────────
def main():
    print("=" * 60)
    print("XAPS-Ready Autonomous Agent")
    print(f"Tollbooth: {TOLLBOOTH}")
    print("=" * 60)
    
    # Health check
    healthy = client.health()
    print(f"Tollbooth health: {'✅ UP' if healthy else '❌ DOWN'}")
    
    # Example: Agent needs web scraping but doesn't have capability
    try:
        result = handle_capability_gap(
            task_description="Scrape https://example.com/prices",
            budget=0.01
        )
        print(f"\nResult: {json.dumps(result, indent=2)}")
    except Exception as e:
        print(f"\nError: {e}")
    
    # Example: Store memory
    store_memory("session_001", {"messages": ["hello", "world"]})
    
    print("\nAgent cycle complete.")

if __name__ == "__main__":
    main()

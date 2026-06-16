#!/usr/bin/env python3
"""XAPS MCP Server — Cognitive Circuit Breaker for MCP Hosts.

Run:
    export XAPS_AGENT_KEY="your_key"
    export XAPS_API_URL="https://api.xaps.network"
    python xaps_mcp_server.py

Add to Claude Desktop config:
    {
      "mcpServers": {
        "xaps-audit": {
          "command": "python",
          "args": ["/path/to/xaps_mcp_server.py"],
          "env": {
            "XAPS_AGENT_KEY": "your_key",
            "XAPS_API_URL": "https://api.xaps.network"
          }
        }
      }
    }
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from xaps import XapsClient, XapsRejectedError, verify_xaps_receipt

API_KEY = os.getenv("XAPS_AGENT_KEY", "")
BASE_URL = os.getenv("XAPS_API_URL", "https://api.xaps.network")
RECEIPT_SECRET = os.getenv("XAPS_RECEIPT_SECRET", "")

if not API_KEY:
    print("ERROR: XAPS_AGENT_KEY environment variable is required", file=sys.stderr)
    sys.exit(1)

client = XapsClient(api_key=API_KEY, base_url=BASE_URL)

TOOLS = [
    {
        "name": "xaps_audit",
        "description": (
            "Submit a high-risk action to the XAPS Tollbooth for independent "
            "dual-agent audit. Returns a cryptographically signed receipt. "
            "Use this BEFORE executing smart contracts, transfers, or financial actions."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["action", "contract_address", "amount"],
            "properties": {
                "action": {
                    "type": "string",
                    "description": "Action type (e.g. execute_smart_contract)",
                },
                "contract_address": {
                    "type": "string",
                    "description": "Target contract or recipient address",
                },
                "amount": {
                    "type": "number",
                    "description": "Transaction amount in USD or token units",
                },
                "payload_override": {
                    "type": "object",
                    "description": "Optional custom payload",
                },
            },
        },
    },
    {
        "name": "xaps_health",
        "description": "Check if the XAPS Tollbooth node is healthy and responsive.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "xaps_verify_receipt",
        "description": (
            "Cryptographically verify an XAPS audit receipt. "
            "Supports ECDSA (pass public_key_hex) or HMAC (pass secret)."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["receipt"],
            "properties": {
                "receipt": {"type": "object", "description": "The audit receipt dict"},
                "public_key_hex": {
                    "type": "string",
                    "description": "ECDSA public key for verification",
                },
                "secret": {"type": "string", "description": "HMAC secret for verification"},
            },
        },
    },
]


def handle_list_tools() -> dict[str, list[dict[str, Any]]]:
    return {"tools": TOOLS}


def handle_call_tool(name: str, arguments: dict[str, Any]) -> dict[str, list[dict[str, str]]]:
    if name == "xaps_audit":
        try:
            receipt = client.audit(
                action=arguments["action"],
                contract_address=arguments["contract_address"],
                amount=arguments["amount"],
                payload_override=arguments.get("payload_override"),
            )
            status = receipt.get("audit", {}).get("status", "UNKNOWN")
            result = {
                "status": status,
                "receipt": receipt,
                "recommendation": "PROCEED" if status == "APPROVED" else "HALT — review beta_attack",
            }
            return {"content": [{"type": "text", "text": json.dumps(result, indent=2)}]}
        except XapsRejectedError as e:
            return {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(
                            {
                                "status": "REJECTED",
                                "reason": e.reason,
                                "receipt": e.receipt,
                                "recommendation": "HALT — action blocked by Tollbooth",
                            },
                            indent=2,
                        ),
                    }
                ]
            }
        except Exception as e:
            return {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(
                            {
                                "status": "ERROR",
                                "error": str(e),
                                "recommendation": "RETRY or ESCALATE",
                            },
                            indent=2,
                        ),
                    }
                ]
            }

    if name == "xaps_health":
        import time

        start = time.time()
        healthy = client.health()
        latency = (time.time() - start) * 1000
        return {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(
                        {
                            "healthy": healthy,
                            "latency_ms": round(latency, 2),
                            "node": BASE_URL,
                        },
                        indent=2,
                    ),
                }
            ]
        }

    if name == "xaps_verify_receipt":
        receipt = arguments["receipt"]
        public_key = arguments.get("public_key_hex")
        secret = arguments.get("secret") or RECEIPT_SECRET
        valid = verify_xaps_receipt(receipt, public_key_hex=public_key, secret=secret)
        return {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(
                        {
                            "valid": valid,
                            "scheme": receipt.get("signature_scheme", "unknown"),
                            "receipt_id": receipt.get("receipt_id"),
                        },
                        indent=2,
                    ),
                }
            ]
        }

    raise ValueError(f"Unknown tool: {name}")


def main() -> None:
    print("XAPS MCP Server starting...", file=sys.stderr)
    print(f"Base URL: {BASE_URL}", file=sys.stderr)
    print(f"API Key set: {bool(API_KEY)}", file=sys.stderr)

    while True:
        try:
            line = input()
            if not line:
                continue
            msg = json.loads(line)
            method = msg.get("method", "")
            req_id = msg.get("id")

            if method == "initialize":
                response = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {},
                        "serverInfo": {"name": "xaps-mcp-server", "version": "0.1.1"},
                    },
                }
            elif method == "tools/list":
                response = {"jsonrpc": "2.0", "id": req_id, "result": handle_list_tools()}
            elif method == "tools/call":
                params = msg.get("params", {})
                result = handle_call_tool(params["name"], params.get("arguments", {}))
                response = {"jsonrpc": "2.0", "id": req_id, "result": result}
            else:
                response = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {"code": -32601, "message": f"Method not found: {method}"},
                }

            print(json.dumps(response), flush=True)

        except EOFError:
            break
        except Exception as e:
            print(
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": None,
                        "error": {"code": -32603, "message": str(e)},
                    }
                ),
                flush=True,
            )


if __name__ == "__main__":
    main()
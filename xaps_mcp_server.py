#!/usr/bin/env python3
"""XAPS MCP Server — Cognitive Circuit Breaker for MCP Hosts.

Run:
    export XAPS_AGENT_KEY="your_key"
    export XAPS_API_URL="https://api.xaps.network"
    xaps-mcp
    # or: python xaps_mcp_server.py

Claude Desktop (macOS config path):
    ~/Library/Application Support/Claude/claude_desktop_config.json
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any, Optional

if os.getenv("XAPS_MCP_DEV"):
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from xaps import XapsClient, XapsRejectedError, verify_xaps_receipt

PROTOCOL_VERSION = "2024-11-05"
SERVER_VERSION = "0.1.1"

API_KEY = os.getenv("XAPS_AGENT_KEY", "")
BASE_URL = os.getenv("XAPS_API_URL", "https://api.xaps.network")
RECEIPT_SECRET = os.getenv("XAPS_RECEIPT_SECRET", "")

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

KNOWN_TOOL_NAMES = {tool["name"] for tool in TOOLS}


def _tool_result(
    payload: dict[str, Any],
    *,
    is_error: bool = False,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "content": [{"type": "text", "text": json.dumps(payload, indent=2)}],
    }
    if is_error:
        result["isError"] = True
    return result


def _jsonrpc_result(req_id: Any, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def _jsonrpc_error(req_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}


def handle_list_tools() -> dict[str, list[dict[str, Any]]]:
    return {"tools": TOOLS}


def handle_call_tool(client: XapsClient, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    if name == "xaps_audit":
        for field in ("action", "contract_address", "amount"):
            if field not in arguments:
                raise ValueError(f"Missing required argument: {field}")

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
            return _tool_result(result, is_error=status != "APPROVED")
        except XapsRejectedError as e:
            return _tool_result(
                {
                    "status": "REJECTED",
                    "reason": e.reason,
                    "receipt": e.receipt,
                    "recommendation": "HALT — action blocked by Tollbooth",
                },
                is_error=True,
            )
        except Exception as e:
            return _tool_result(
                {
                    "status": "ERROR",
                    "error": str(e),
                    "recommendation": "RETRY or ESCALATE",
                },
                is_error=True,
            )

    if name == "xaps_health":
        import time

        start = time.time()
        healthy = client.health()
        latency = (time.time() - start) * 1000
        return _tool_result(
            {
                "healthy": healthy,
                "latency_ms": round(latency, 2),
                "node": BASE_URL,
            },
            is_error=not healthy,
        )

    if name == "xaps_verify_receipt":
        if "receipt" not in arguments:
            raise ValueError("Missing required argument: receipt")
        receipt = arguments["receipt"]
        public_key = arguments.get("public_key_hex")
        secret = arguments.get("secret") or RECEIPT_SECRET
        valid = verify_xaps_receipt(receipt, public_key_hex=public_key, secret=secret)
        return _tool_result(
            {
                "valid": valid,
                "scheme": receipt.get("signature_scheme", "unknown"),
                "receipt_id": receipt.get("receipt_id"),
            },
            is_error=not valid,
        )

    raise ValueError(f"Unknown tool: {name}")


def handle_initialize(params: dict[str, Any]) -> dict[str, Any]:
    client_version = params.get("protocolVersion", PROTOCOL_VERSION)
    if client_version != PROTOCOL_VERSION:
        print(
            f"WARNING: client protocolVersion {client_version!r} != server {PROTOCOL_VERSION!r}",
            file=sys.stderr,
        )
    return {
        "protocolVersion": PROTOCOL_VERSION,
        "capabilities": {"tools": {}},
        "serverInfo": {"name": "xaps-mcp-server", "version": SERVER_VERSION},
    }


def dispatch_message(msg: dict[str, Any], client: XapsClient) -> Optional[dict[str, Any]]:
    """Return a JSON-RPC response, or None for notifications (no response)."""
    method = msg.get("method", "")
    req_id = msg.get("id")

    if req_id is None:
        if method.startswith("notifications/"):
            return None
        return None

    if method == "initialize":
        params = msg.get("params") or {}
        return _jsonrpc_result(req_id, handle_initialize(params))

    if method == "ping":
        return _jsonrpc_result(req_id, {})

    if method == "tools/list":
        return _jsonrpc_result(req_id, handle_list_tools())

    if method == "tools/call":
        params = msg.get("params")
        if not isinstance(params, dict):
            return _jsonrpc_error(req_id, -32602, "Invalid params: expected object")
        name = params.get("name")
        if not name:
            return _jsonrpc_error(req_id, -32602, "Invalid params: missing tool name")
        if name not in KNOWN_TOOL_NAMES:
            return _jsonrpc_error(req_id, -32602, f"Unknown tool: {name}")
        arguments = params.get("arguments") or {}
        if not isinstance(arguments, dict):
            return _jsonrpc_error(req_id, -32602, "Invalid params: arguments must be an object")
        try:
            result = handle_call_tool(client, name, arguments)
            return _jsonrpc_result(req_id, result)
        except ValueError as e:
            return _jsonrpc_error(req_id, -32602, str(e))
        except Exception as e:
            return _jsonrpc_error(req_id, -32603, str(e))

    if method.startswith("notifications/"):
        return None

    return _jsonrpc_error(req_id, -32601, f"Method not found: {method}")


def main() -> None:
    if not API_KEY:
        print("ERROR: XAPS_AGENT_KEY environment variable is required", file=sys.stderr)
        sys.exit(1)

    client = XapsClient(api_key=API_KEY, base_url=BASE_URL)

    print("XAPS MCP Server starting...", file=sys.stderr)
    print(f"Base URL: {BASE_URL}", file=sys.stderr)
    print(f"API Key set: {bool(API_KEY)}", file=sys.stderr)

    while True:
        try:
            line = input()
            if not line:
                continue
            msg = json.loads(line)
            response = dispatch_message(msg, client)
            if response is not None:
                print(json.dumps(response), flush=True)

        except EOFError:
            break
        except json.JSONDecodeError as e:
            print(
                json.dumps(_jsonrpc_error(None, -32700, f"Parse error: {e}")),
                flush=True,
            )
        except Exception as e:
            print(
                json.dumps(_jsonrpc_error(None, -32603, str(e))),
                flush=True,
            )


if __name__ == "__main__":
    main()
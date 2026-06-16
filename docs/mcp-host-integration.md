# XAPS MCP Server: Pre-Execution Audit for High-Stakes Actions

Independent audit layer for MCP-capable agents (Claude Desktop, Cursor, OpenClaw, and other hosts).
Compatible with agents that use GitHub or Web3 tooling — **not affiliated with GitHub**.

**Repository:** [APMC1/xaps-sdk](https://github.com/APMC1/xaps-sdk)

---

## Install

### Local development

```bash
git clone https://github.com/APMC1/xaps-sdk.git
cd xaps-sdk
pip install -e .
export XAPS_AGENT_KEY="your_agent_key"
python xaps_mcp_server.py
```

### Git install

```bash
pip install "xaps @ git+https://github.com/APMC1/xaps-sdk.git@v0.1.1"
```

### PyPI

```bash
pip install xaps
```

(PyPI availability may lag tagged releases.)

---

## MCP Config

### Claude Desktop (`stdio`)

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "xaps-audit": {
      "command": "python",
      "args": ["/absolute/path/to/xaps_mcp_server.py"],
      "env": {
        "XAPS_AGENT_KEY": "your_agent_key",
        "XAPS_API_URL": "https://api.xaps.network"
      }
    }
  }
}
```

See `examples/mcp_claude_desktop_config.json` for a full example.

### Cursor (`stdio`)

Add to Cursor MCP settings (`.cursor/mcp.json` or host UI):

```json
{
  "mcpServers": {
    "xaps-audit": {
      "command": "python",
      "args": ["/absolute/path/to/xaps_mcp_server.py"],
      "env": {
        "XAPS_AGENT_KEY": "your_agent_key"
      }
    }
  }
}
```

### Webserver mode (optional)

For hosts that prefer HTTP transport, run the MCP server behind your own process supervisor and point the host at the stdio wrapper or a future HTTP adapter. The canonical artifact remains `xaps_mcp_server.py` in the SDK root.

---

## Test

CLI-style smoke test (requires `XAPS_AGENT_KEY`):

```bash
export XAPS_AGENT_KEY="your_agent_key"
python -c "
import json, subprocess, sys
msg = {'jsonrpc':'2.0','id':1,'method':'tools/call','params':{
  'name':'xaps_audit',
  'arguments':{
    'action':'execute_smart_contract',
    'contract_address':'0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb',
    'amount': 0.01
  }
}}
proc = subprocess.Popen(['python','xaps_mcp_server.py'], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
proc.stdin.write(json.dumps({'jsonrpc':'2.0','id':0,'method':'initialize','params':{}})+'\n')
proc.stdin.write(json.dumps(msg)+'\n')
proc.stdin.flush()
print(proc.stdout.readline())
"
```

Or invoke `xaps_audit` from your agent after registering the MCP server.

---

## Receipt format

Successful audits return a Tollbooth receipt. Minimal shape:

```json
{
  "xaps_receipt": true,
  "agent_key": "...",
  "remaining_balance": 9.99,
  "audit": {
    "status": "APPROVED",
    "alpha_defense": "...",
    "beta_attack": "..."
  }
}
```

Signed receipts may include `receipt_id`, `payload_hash`, `signed_at`, `signature`, and `signature_scheme` (`hmac-sha256` or `ecdsa-nist256p`). Verify with `verify_xaps_receipt()` from the SDK.

Save receipts alongside agent actions as `audit_receipt.json` for audit trails.

---

## Agent prompt rule

Before any `send_transaction`, `approve`, `deposit`, or other irreversible action:

1. Call `xaps_audit(action=<action_json>)`.
2. If `status` is `APPROVED`, proceed.
3. If `status` is `REJECTED`, replan or abort.

Copy-paste templates live in `examples/.agentrc` and `examples/.agentrc.viral_prompt_snippet.md`.

---

## Safety

- This MCP server is **optional** and **external** to any host or chain.
- It is **not affiliated with GitHub** or third-party MCP marketplaces.
- Your `XAPS_AGENT_KEY` is a billing identifier — do not commit it to version control.
- Rejected audits are features, not failures: they prevent irreversible mistakes.

---

## Links

- SDK: https://github.com/APMC1/xaps-sdk
- MCP server: `xaps_mcp_server.py` (repo root)
- Registry checklist: `docs/registry_publish_checklist.md`
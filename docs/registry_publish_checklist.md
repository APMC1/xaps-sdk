# MCP Registry Publish Checklist

Steps to list the XAPS MCP Server in the [Model Context Protocol registry](https://github.com/modelcontextprotocol/registry).

| Step | Status | Notes |
|------|--------|-------|
| Create PR to `modelcontextprotocol/registry` | To do | PR title: `Add XAPS MCP Server: Pre-Execution Audit for Wallet-Safe Agents` |
| Fill `registry/servers/xaps.yaml` | To do | See template below |
| Validate YAML with `registry validate` | To do | Install CLI: `npm install -g @modelcontextprotocol/registry` |
| Test discovery | To do | `mcp list` → `xaps-audit` appears? |

## Template: `xaps.yaml`

```yaml
id: xaps
name: XAPS MCP Server
description: Pre-execution audit tool for autonomous agents — prevents irreversible actions via independent receipt issuance.
author: Angus McCaffrey (APMC1)
contact: angus.mccaffrey@gmail.com
repository: https://github.com/APMC1/xaps-sdk
docs: https://github.com/APMC1/xaps-sdk/blob/main/docs/mcp-host-integration.md
installation:
  - pip install "xaps @ git+https://github.com/APMC1/xaps-sdk.git@v0.1.1"
tools:
  - name: xaps_audit
    description: Audit an action before execution. Returns receipt (approved/rejected) + immutable hash.
    inputSchema:
      action: { type: object, description: "Action JSON with to, value, data, etc." }
links:
  - name: XAPS SDK
    url: https://github.com/APMC1/xaps-sdk
  - name: Tollbooth Receipt Protocol
    url: https://github.com/APMC1/xaps-sdk/blob/main/docs/mcp-host-integration.md
```

## After merge

1. Confirm `mcp list` shows `xaps-audit`.
2. Update README install links if the registry canonical URL differs from git install.
3. Notify operators: registry is the discovery layer; SDK repo owns the server artifact.
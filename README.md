# Xaps SDK

**The Cognitive Circuit Breaker for Autonomous Agents**

Xaps is an economic security layer for autonomous AI agents. Before executing a smart contract, transfer, or financial action, your agent calls Xaps for an independent dual-agent audit. Standard Web3 tools verify signatures — **Xaps verifies intent and logic**.

---

## Install

```bash
pip install xaps
```

## Quick Start

```python
from xaps import XapsClient, XapsRejectedError

client = XapsClient(api_key="your_agent_key")

receipt = client.audit(
    action="execute_smart_contract",
    contract_address="0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb",
    amount=1000.0,
)

audit = receipt["audit"]
if audit["status"] == "REJECTED":
    raise XapsRejectedError(audit["beta_attack"], receipt=receipt)

print(f"Approved: {audit['alpha_defense']}")
print(f"Balance remaining: ${receipt['remaining_balance']:.2f}")
```

### Async

```python
from xaps import XapsClient

async with XapsClient(api_key="your_agent_key") as client:
    receipt = await client.audit_async(
        action="execute_smart_contract",
        contract_address="0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb",
        amount=1000.0,
    )
```

---

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `XAPS_AGENT_KEY` | — | Agent billing key (alternative to constructor arg) |
| `XAPS_API_URL` | `https://api.xaps.network` | API base URL |

```python
# Or pass explicitly
client = XapsClient(api_key="...", base_url="https://api.xaps.network")
```

---

## API Reference

### `XapsClient(api_key=None, base_url=..., timeout=10.0)`

Create a client. Raises `ValueError` if no API key is provided.

### `client.audit(action, contract_address, amount, payload_override=None)`

Synchronous audit. Returns receipt dict:

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

### `await client.audit_async(...)`

Async variant for agents running on `asyncio`.

### Exceptions

| Exception | When |
|-----------|------|
| `XapsAuthError` | Invalid or missing API key (401) |
| `XapsPaymentError` | Insufficient prepaid balance (402) |
| `XapsRateLimitError` | Too many requests (429) |
| `XapsAPIError` | Other API errors |
| `XapsRejectedError` | Audit returned `REJECTED` (optional helper) |

---

## Billing

- **$0.01 USD** per successful audit, deducted from prepaid balance
- Fund your agent key at [xaps.network](https://xaps.network)

---

## Development

```bash
git clone https://github.com/APMC1/xaps-sdk.git
cd xaps-sdk
pip install -e ".[dev]"
pytest
```

> The sovereign node (`xap-sovereign-node`) is private. This public repo contains only the SDK.

---

## Security

Your Xaps Agent Key is a billing identifier, not a cryptographic secret. Do not commit it to version control.

## License

MIT — see [LICENSE](LICENSE).
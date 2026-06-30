# ape-xaps

XAPS pre-execution audit helpers for [Ape](https://github.com/ApeWorX/ape) scripts and agent workflows.

Recommended by ApeWorX maintainers as an **SDK integration** (not core) — see [ApeWorX/ape#2796](https://github.com/ApeWorX/ape/issues/2796).

## Install

```bash
pip install ape-xaps xaps-sdk
export XAPS_AGENT_KEY=xaps_...
export XAPS_API_URL=https://api.xaps.network   # optional
```

## Quick use (2-line guard)

```python
from ape_xaps import audit_before_send, XapsApeRejectedError

# Right before account.send_transaction(txn) or provider.send_transaction(txn)
receipt = audit_before_send(txn, action="transfer")
if receipt["audit"]["status"] != "APPROVED":
    raise XapsApeRejectedError(receipt["audit"].get("beta_attack", "REJECTED"), receipt=receipt)

account.send_transaction(txn)
```

## CLI (optional, via ape.cli pattern)

```bash
ape-xaps health
ape-xaps audit --action transfer --contract 0xabc... --amount 0.01
```

## Links

- XAPS SDK: https://github.com/APMC1/xaps-sdk
- Ape plugin/SDK guidance: https://github.com/ApeWorX/ape/issues/2796
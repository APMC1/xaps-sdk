"""CLI for ape-xaps — optional ergonomics alongside SDK use in Ape scripts."""

from __future__ import annotations

import json
import os
import sys

import click

from xaps import XapsClient

from .guard import audit_transaction


@click.group()
def cli() -> None:
    """XAPS audit helpers for Ape workflows."""


@cli.command("health")
def health_cmd() -> None:
    """Check Tollbooth reachability."""
    key = os.getenv("XAPS_AGENT_KEY", "")
    if not key:
        click.echo("XAPS_AGENT_KEY not set", err=True)
        sys.exit(1)
    with XapsClient(api_key=key) as client:
        ok = client.health()
    click.echo("ok" if ok else "degraded")
    sys.exit(0 if ok else 2)


@cli.command("audit")
@click.option("--action", default="transfer", show_default=True)
@click.option("--contract", "contract_address", required=True)
@click.option("--amount", default=0.01, type=float, show_default=True)
@click.option("--json", "as_json", is_flag=True, help="Print raw receipt JSON")
def audit_cmd(action: str, contract_address: str, amount: float, as_json: bool) -> None:
    """Run a standalone Tollbooth audit (no Ape txn object required)."""
    key = os.getenv("XAPS_AGENT_KEY", "")
    if not key:
        click.echo("XAPS_AGENT_KEY not set", err=True)
        sys.exit(1)

    with XapsClient(api_key=key) as client:
        receipt = client.audit(
            action=action,
            contract_address=contract_address,
            amount=amount,
            payload_override={"source": "ape-xaps-cli", "action": action},
        )

    status = receipt.get("audit", {}).get("status", receipt.get("status", "UNKNOWN"))
    if as_json:
        click.echo(json.dumps(receipt, indent=2, default=str))
    else:
        click.echo(f"status={status}")
    if str(status).upper() != "APPROVED":
        sys.exit(1)


if __name__ == "__main__":
    cli()
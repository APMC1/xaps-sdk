"""Xaps SDK client for the Sovereign Node /verify API."""

from __future__ import annotations

import os
from typing import Any, Optional

import httpx

DEFAULT_BASE_URL = os.getenv("XAPS_API_URL", "https://api.xaps.network")


class XapsError(Exception):
    """Base exception for Xaps SDK errors."""


class XapsAuthError(XapsError, PermissionError):
    """401 — invalid or missing X-Agent-Key."""


class XapsPaymentError(XapsError, PermissionError):
    """402 — insufficient prepaid balance."""


class XapsRateLimitError(XapsError, ConnectionError):
    """429 — rate limit exceeded."""


class XapsAPIError(XapsError, RuntimeError):
    """Non-success HTTP response from the API."""


class XapsRejectedError(XapsError):
    """Audit returned REJECTED status."""

    def __init__(self, reason: str, receipt: Optional[dict[str, Any]] = None) -> None:
        self.reason = reason
        self.receipt = receipt
        super().__init__(reason)


class XapsClient:
    """Client for the Xaps Sovereign Node tollbooth API."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        *,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = 10.0,
    ) -> None:
        key = (api_key or os.getenv("XAPS_AGENT_KEY") or "").strip()
        if not key:
            raise ValueError(
                "api_key is required (pass to constructor or set XAPS_AGENT_KEY)"
            )
        self.api_key = key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._sync: Optional[httpx.Client] = None
        self._async: Optional[httpx.AsyncClient] = None

    def _headers(self) -> dict[str, str]:
        return {
            "X-Agent-Key": self.api_key,
            "Content-Type": "application/json",
        }

    @staticmethod
    def _build_payload(
        action: str,
        contract_address: str,
        amount: float,
        payload_override: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        if payload_override is not None:
            return payload_override
        return {
            "action": action,
            "contract_address": contract_address,
            "amount": amount,
        }

    @staticmethod
    def _parse_error_detail(response: httpx.Response) -> str:
        try:
            body = response.json()
            if isinstance(body, dict):
                return str(body.get("detail", response.text))
        except Exception:
            pass
        return response.text or f"HTTP {response.status_code}"

    def _raise_for_status(self, response: httpx.Response) -> None:
        if response.status_code == 401:
            raise XapsAuthError("Invalid or missing X-Agent-Key")
        if response.status_code == 402:
            raise XapsPaymentError(self._parse_error_detail(response))
        if response.status_code == 429:
            raise XapsRateLimitError("Rate limit exceeded — slow down")
        if response.status_code >= 400:
            raise XapsAPIError(
                f"API error {response.status_code}: {self._parse_error_detail(response)}"
            )

    @property
    def _sync_client(self) -> httpx.Client:
        if self._sync is None:
            self._sync = httpx.Client(
                base_url=self.base_url,
                timeout=self.timeout,
                headers=self._headers(),
            )
        return self._sync

    @property
    def _async_client(self) -> httpx.AsyncClient:
        if self._async is None:
            self._async = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.timeout,
                headers=self._headers(),
            )
        return self._async

    def audit(
        self,
        action: str,
        contract_address: str,
        amount: float,
        *,
        payload_override: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Run a synchronous dual-agent audit via POST /verify."""
        payload = self._build_payload(
            action, contract_address, amount, payload_override
        )
        try:
            response = self._sync_client.post("/verify", json={"payload": payload})
        except httpx.TimeoutException as exc:
            raise XapsAPIError(f"Request timed out after {self.timeout}s") from exc
        except httpx.HTTPError as exc:
            raise XapsAPIError(f"Connection failed: {exc}") from exc

        self._raise_for_status(response)
        return response.json()

    async def audit_async(
        self,
        action: str,
        contract_address: str,
        amount: float,
        *,
        payload_override: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Run an async dual-agent audit via POST /verify."""
        payload = self._build_payload(
            action, contract_address, amount, payload_override
        )
        try:
            response = await self._async_client.post(
                "/verify", json={"payload": payload}
            )
        except httpx.TimeoutException as exc:
            raise XapsAPIError(f"Request timed out after {self.timeout}s") from exc
        except httpx.HTTPError as exc:
            raise XapsAPIError(f"Connection failed: {exc}") from exc

        self._raise_for_status(response)
        return response.json()

    def health(self) -> bool:
        """Return True if the API responds (best-effort)."""
        try:
            r = self._sync_client.get("/docs", timeout=3.0)
            return r.status_code < 500
        except httpx.HTTPError:
            return False

    def close(self) -> None:
        if self._sync is not None:
            self._sync.close()
            self._sync = None

    async def aclose(self) -> None:
        if self._async is not None:
            await self._async.aclose()
            self._async = None
        self.close()

    def __enter__(self) -> XapsClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    async def __aenter__(self) -> XapsClient:
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.aclose()


# ============================================================
# Receipt Verification Helpers (opt-in, added for ECDSA hardening)
# These are pure functions — clients call them explicitly after audit().
# No changes to XapsClient.audit() or existing behavior.
# ============================================================

import hashlib
import hmac
import json

try:
    from loguru import logger
except Exception:
    import warnings
    logger = type("logger", (), {"warning": lambda *a, **k: warnings.warn(str(a[0]) if a else "", UserWarning)})()

def _canonical_receipt_message_for_verify(receipt: dict) -> str:
    """Stable JSON canonicalization used for ECDSA verification.
    (HMAC path uses the original colon string inside verify_receipt_hmac for legacy compatibility.)
    """
    return json.dumps({
        "receipt_id": receipt["receipt_id"],
        "agent_key": receipt["agent_key"],
        "payload_hash": receipt["payload_hash"],
        "status": receipt["status"],
        "signed_at": receipt["signed_at"],
    }, sort_keys=True, separators=(',', ':'))


def verify_receipt_ecdsa(receipt: dict, public_key_hex: str) -> bool:
    """
    Verify an ECDSA (NIST256p) signed Xaps receipt.
    Returns False on any error (never raises).
    """
    try:
        from ecdsa import VerifyingKey, NIST256p, SignatureError
        vk = VerifyingKey.from_string(
            bytes.fromhex(public_key_hex),
            curve=NIST256p,
            hashfunc=hashlib.sha256
        )
        sig = bytes.fromhex(receipt["signature"])
        message = _canonical_receipt_message_for_verify(receipt)
        vk.verify(sig, message.encode(), hashfunc=hashlib.sha256)
        return True
    except (SignatureError, ValueError, Exception):
        return False


def verify_receipt_hmac(receipt: dict, secret: str) -> bool:
    """
    Verify an HMAC-signed receipt using the node's shared secret.
    ⚠️ Only parties who know the secret (node operator) can do this.
    Returns False on error.
    """
    try:
        message = f"{receipt['receipt_id']}:{receipt['agent_key']}:{receipt['payload_hash']}:{receipt['status']}:{receipt['signed_at']}"
        expected = hmac.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(receipt.get("signature", ""), expected)
    except Exception:
        return False


def verify_xaps_receipt(receipt: dict, *, public_key_hex: str | None = None, secret: str | None = None) -> bool:
    """
    Verify an Xaps receipt.
    - ECDSA receipts (signature_scheme == "ecdsa-nist256p"): pass public_key_hex (from /oracle-public-key or the receipt itself)
    - HMAC receipts: pass the node's XAPS_RECEIPT_SECRET (only the operator should have it)
    - Unknown/missing scheme: returns False
    """
    scheme = receipt.get("signature_scheme", "hmac-sha256")
    if scheme == "ecdsa-nist256p":
        if not public_key_hex:
            logger.warning("ECDSA receipt but no public_key_hex provided for verification.")
            return False
        return verify_receipt_ecdsa(receipt, public_key_hex)
    elif scheme == "hmac-sha256":
        if not secret:
            logger.warning("HMAC receipt but no secret provided for verification.")
            return False
        return verify_receipt_hmac(receipt, secret)
    else:
        logger.warning(f"Unknown signature_scheme in receipt: {scheme}")
        return False

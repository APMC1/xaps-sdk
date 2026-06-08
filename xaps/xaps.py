"""Xaps SDK client for the Sovereign Node /verify API."""

from __future__ import annotations

import os
import hmac
import hashlib
import json
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


def _receipt_secret() -> str:
    secret = os.getenv("XAPS_RECEIPT_SECRET") or os.getenv("BANK_WEBHOOK_SECRET")
    if not secret:
        raise ValueError(
            "XAPS_RECEIPT_SECRET (or BANK_WEBHOOK_SECRET) not set in environment."
        )
    return secret


def sign_node_receipt(
    receipt_id: str,
    agent_key: str,
    payload_hash: str,
    status: str,
    signed_at: str,
    *,
    secret: Optional[str] = None,
) -> str:
    """Reproduce the node's HMAC signature (for testing). Matches src/main.py."""
    key = secret or _receipt_secret()
    message = f"{receipt_id}:{agent_key}:{payload_hash}:{status}:{signed_at}"
    return hmac.new(key.encode(), message.encode(), hashlib.sha256).hexdigest()


def verify_node_receipt(
    receipt_id: str,
    agent_key: str,
    payload_hash: str,
    status: str,
    signed_at: str,
    signature: str,
    *,
    secret: Optional[str] = None,
) -> bool:
    """Verify a /verify response signature from the Xaps Sovereign Node."""
    expected = sign_node_receipt(
        receipt_id, agent_key, payload_hash, status, signed_at, secret=secret
    )
    return hmac.compare_digest(expected, signature)


def verify_xaps_receipt(receipt_data: dict[str, Any], provided_signature: str) -> bool:
    """
    Verify a full /verify API response dict (uses receipt_id, signature, etc.).
    """
    required = ("receipt_id", "agent_key", "payload_hash", "signed_at", "signature")
    audit = receipt_data.get("audit") or {}
    status = audit.get("status") or receipt_data.get("status")
    if not all(receipt_data.get(k) for k in required) or not status:
        raise ValueError(f"Receipt missing required fields: {required + ('audit.status',)}")

    return verify_node_receipt(
        receipt_id=receipt_data["receipt_id"],
        agent_key=receipt_data["agent_key"],
        payload_hash=receipt_data["payload_hash"],
        status=status,
        signed_at=receipt_data["signed_at"],
        signature=receipt_data["signature"],
    )

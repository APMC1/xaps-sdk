"""Xaps SDK client for the Sovereign Node /verify API."""

from __future__ import annotations

import json
import os
import time
from typing import Any, Optional

import httpx

DEFAULT_BASE_URL = os.getenv("XAPS_API_URL", "https://api.xaps.network")

# B1 fast-verify allowlist — must match Tollbooth FAST_ALLOWLIST server default.
FAST_ALLOWLIST = frozenset(
    a.strip()
    for a in os.getenv(
        "XAPS_FAST_ALLOWLIST",
        "query_oracle,fast_reason,scout_read,github_create_issue",
    ).split(",")
    if a.strip()
)


def is_fast_allowlisted(action: str) -> bool:
    """Return True if action is eligible for POST /verify/fast."""
    return action in FAST_ALLOWLIST


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
        payload = {
            "action": action,
            "contract_address": contract_address,
            "amount": amount,
        }
        if payload_override is not None:
            payload.update(payload_override)
        return payload

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

    def _post_audit(
        self,
        path: str,
        action: str,
        contract_address: str,
        amount: float,
        *,
        payload_override: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        payload = self._build_payload(
            action, contract_address, amount, payload_override
        )
        try:
            response = self._sync_client.post(path, json={"payload": payload})
        except httpx.TimeoutException as exc:
            raise XapsAPIError(f"Request timed out after {self.timeout}s") from exc
        except httpx.HTTPError as exc:
            raise XapsAPIError(f"Connection failed: {exc}") from exc

        self._raise_for_status(response)
        return response.json()

    async def _post_audit_async(
        self,
        path: str,
        action: str,
        contract_address: str,
        amount: float,
        *,
        payload_override: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        payload = self._build_payload(
            action, contract_address, amount, payload_override
        )
        try:
            response = await self._async_client.post(
                path, json={"payload": payload}
            )
        except httpx.TimeoutException as exc:
            raise XapsAPIError(f"Request timed out after {self.timeout}s") from exc
        except httpx.HTTPError as exc:
            raise XapsAPIError(f"Connection failed: {exc}") from exc

        self._raise_for_status(response)
        return response.json()

    def audit(
        self,
        action: str,
        contract_address: str,
        amount: float,
        *,
        payload_override: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Run a synchronous dual-agent audit via POST /verify."""
        return self._post_audit(
            "/verify", action, contract_address, amount, payload_override=payload_override
        )

    def audit_fast(
        self,
        action: str,
        contract_address: str,
        amount: float,
        *,
        payload_override: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Run a rule-only fast audit via POST /verify/fast (allowlisted actions only)."""
        if not is_fast_allowlisted(action):
            raise XapsAPIError(
                f"action '{action}' is not fast-eligible; use audit() for full swarm path. "
                f"Allowlist: {sorted(FAST_ALLOWLIST)}"
            )
        return self._post_audit(
            "/verify/fast",
            action,
            contract_address,
            amount,
            payload_override=payload_override,
        )

    def audit_auto(
        self,
        action: str,
        contract_address: str,
        amount: float,
        *,
        payload_override: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Route to /verify/fast when allowlisted, else /verify."""
        if is_fast_allowlisted(action):
            return self.audit_fast(
                action, contract_address, amount, payload_override=payload_override
            )
        return self.audit(
            action, contract_address, amount, payload_override=payload_override
        )

    async def audit_async(
        self,
        action: str,
        contract_address: str,
        amount: float,
        *,
        payload_override: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Run an async dual-agent audit via POST /verify."""
        return await self._post_audit_async(
            "/verify", action, contract_address, amount, payload_override=payload_override
        )

    async def audit_fast_async(
        self,
        action: str,
        contract_address: str,
        amount: float,
        *,
        payload_override: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Async rule-only fast audit via POST /verify/fast."""
        if not is_fast_allowlisted(action):
            raise XapsAPIError(
                f"action '{action}' is not fast-eligible; use audit_async() for full swarm. "
                f"Allowlist: {sorted(FAST_ALLOWLIST)}"
            )
        return await self._post_audit_async(
            "/verify/fast",
            action,
            contract_address,
            amount,
            payload_override=payload_override,
        )

    async def audit_auto_async(
        self,
        action: str,
        contract_address: str,
        amount: float,
        *,
        payload_override: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Async route: /verify/fast when allowlisted, else /verify."""
        if is_fast_allowlisted(action):
            return await self.audit_fast_async(
                action, contract_address, amount, payload_override=payload_override
            )
        return await self.audit_async(
            action, contract_address, amount, payload_override=payload_override
        )

    @classmethod
    def register(
        cls,
        *,
        base_url: str = DEFAULT_BASE_URL,
        proposed_key: Optional[str] = None,
        wallet_address: Optional[str] = None,
        chain: Optional[str] = None,
        timeout: float = 10.0,
    ) -> tuple["XapsClient", dict[str, Any]]:
        """Self-serve onboarding via POST /agents/register."""
        payload: dict[str, Any] = {}
        if proposed_key:
            payload["agent_key"] = proposed_key.strip()
        if wallet_address:
            payload["wallet_address"] = wallet_address.strip()
        if chain:
            payload["chain"] = chain.strip()
        try:
            response = httpx.post(
                f"{base_url.rstrip('/')}/agents/register",
                json=payload,
                timeout=timeout,
            )
        except httpx.TimeoutException as exc:
            raise XapsAPIError(f"Request timed out after {timeout}s") from exc
        except httpx.HTTPError as exc:
            raise XapsAPIError(f"Connection failed: {exc}") from exc

        if response.status_code == 409:
            raise XapsAPIError("Agent key already registered")
        if response.status_code >= 400:
            try:
                body = response.json()
                detail = body.get("detail", response.text)
            except Exception:
                detail = response.text
            raise XapsAPIError(f"Registration failed ({response.status_code}): {detail}")

        data = response.json()
        agent_key = str(data.get("agent_key", "")).strip()
        if not agent_key:
            raise XapsAPIError("Registration response missing agent_key")
        return cls(api_key=agent_key, base_url=base_url, timeout=timeout), data

    @classmethod
    def bootstrap(
        cls,
        *,
        base_url: str = DEFAULT_BASE_URL,
        wallet_address: Optional[str] = None,
        chain: Optional[str] = None,
        timeout: float = 10.0,
    ) -> tuple["XapsClient", dict[str, Any]]:
        """Autonomous onboarding: reuse env key or register, then return funding options."""
        existing = (os.getenv("XAPS_AGENT_KEY") or "").strip()
        if existing:
            client = cls(api_key=existing, base_url=base_url, timeout=timeout)
            info = client.get_funding_options()
            return client, {"reused_key": True, "agent_key": existing, **info}
        client, reg = cls.register(
            base_url=base_url,
            wallet_address=wallet_address,
            chain=chain,
            timeout=timeout,
        )
        funding = client.get_funding_options()
        return client, {"reused_key": False, **reg, "funding": funding}

    def get_funding_options(self) -> dict[str, Any]:
        """Return deposit rails and balance breakdown."""
        try:
            response = self._sync_client.get("/agents/funding-options")
        except httpx.TimeoutException as exc:
            raise XapsAPIError(f"Request timed out after {self.timeout}s") from exc
        except httpx.HTTPError as exc:
            raise XapsAPIError(f"Connection failed: {exc}") from exc
        self._raise_for_status(response)
        return response.json()

    def link_wallet(self, wallet_address: str, chain: Optional[str] = None) -> dict[str, Any]:
        payload: dict[str, Any] = {"wallet_address": wallet_address.strip()}
        if chain:
            payload["chain"] = chain.strip()
        try:
            response = self._sync_client.post("/agents/link-wallet", json=payload)
        except httpx.TimeoutException as exc:
            raise XapsAPIError(f"Request timed out after {self.timeout}s") from exc
        except httpx.HTTPError as exc:
            raise XapsAPIError(f"Connection failed: {exc}") from exc
        self._raise_for_status(response)
        return response.json()

    def wait_for_balance(
        self,
        min_usd: float = 0.01,
        *,
        timeout: float = 300.0,
        poll_interval: float = 10.0,
    ) -> float:
        """Poll balance until min_usd reached or timeout."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            balance = self.get_balance()
            if balance >= min_usd:
                return balance
            time.sleep(poll_interval)
        raise XapsAPIError(f"Balance still below ${min_usd} after {timeout}s")

    def ensure_funded(self, min_usd: float = 0.01) -> float:
        """Return balance or raise with funding options embedded in message."""
        balance = self.get_balance()
        if balance >= min_usd:
            return balance
        try:
            options = self.get_funding_options()
        except XapsAPIError:
            options = {}
        raise XapsPaymentError(
            f"Insufficient balance ${balance:.4f} (need ${min_usd}). "
            f"Funding options: {options.get('rails', options)}"
        )

    def get_balance(self) -> float:
        """Return prepaid USD balance for the configured agent key."""
        try:
            response = self._sync_client.get("/agents/balance")
        except httpx.TimeoutException as exc:
            raise XapsAPIError(f"Request timed out after {self.timeout}s") from exc
        except httpx.HTTPError as exc:
            raise XapsAPIError(f"Connection failed: {exc}") from exc

        self._raise_for_status(response)
        body = response.json()
        balance = body.get("balance_usd")
        if balance is None:
            raise XapsAPIError("Balance response missing balance_usd")
        return float(balance)

    def create_checkout(self, amount_usd: float) -> dict[str, Any]:
        """Create a Stripe Checkout session for prepaid credits."""
        try:
            response = self._sync_client.post(
                "/agents/checkout",
                json={"amount_usd": amount_usd},
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
            r = self._sync_client.get("/health", timeout=3.0)
            return r.status_code < 500
        except httpx.HTTPError:
            return False

    def fetch_oracle_public_key(self) -> Optional[str]:
        """GET /oracle-public-key from the Tollbooth (for receipt verify)."""
        try:
            r = self._sync_client.get("/oracle-public-key", timeout=5.0)
            if r.status_code == 404:
                return None
            self._raise_for_status(r)
            body = r.json()
            key = body.get("oracle_public_key_hex")
            return str(key).strip() if key else None
        except httpx.HTTPError as exc:
            raise XapsAPIError(f"Connection failed: {exc}") from exc

    def query_sink(
        self,
        query: str,
        receipt: dict[str, Any],
        *,
        oracle_url: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> dict[str, Any]:
        """POST a receipt-gated query to the subsidized Sink Oracle.

        Args:
            query: Natural-language or structured data request.
            receipt: Tollbooth audit receipt (from audit / audit_fast / audit_auto).
            oracle_url: Sink base URL (default XAPS_ORACLE_URL or localhost:8766).
        """
        base = (
            oracle_url
            or os.getenv("XAPS_ORACLE_URL")
            or "http://localhost:8766"
        ).rstrip("/")
        url = base if base.endswith("/oracle/query") else f"{base}/oracle/query"
        t = timeout if timeout is not None else max(self.timeout, 30.0)
        try:
            response = httpx.post(
                url,
                json={"query": query, "receipt": receipt},
                headers={
                    "Content-Type": "application/json",
                    "XAPS-Receipt": json.dumps(receipt, default=str),
                },
                timeout=t,
            )
        except httpx.TimeoutException as exc:
            raise XapsAPIError(f"Sink request timed out after {t}s") from exc
        except httpx.HTTPError as exc:
            raise XapsAPIError(f"Sink connection failed: {exc}") from exc

        if response.status_code == 403:
            raise XapsAuthError(
                f"Sink rejected receipt: {self._parse_error_detail(response)}"
            )
        if response.status_code == 409:
            raise XapsAPIError(
                f"Sink receipt replay: {self._parse_error_detail(response)}"
            )
        if response.status_code >= 400:
            raise XapsAPIError(
                f"Sink error {response.status_code}: {self._parse_error_detail(response)}"
            )
        return response.json()

    def audit_then_query(
        self,
        query: str,
        *,
        amount: float = 0.01,
        contract_address: str = "",
        action: str = "query_oracle",
        oracle_url: Optional[str] = None,
        use_fast: bool = True,
        payload_override: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Adoption-magnet path: Tollbooth audit (or fast) then Sink query.

        Returns::
            {
              "receipt": {...},
              "sink": {...},   # oracle response
              "query": str,
            }

        Raises XapsRejectedError if the audit is REJECTED.
        """
        override = {"query": query, **(payload_override or {})}
        if use_fast and is_fast_allowlisted(action):
            receipt = self.audit_fast(
                action, contract_address, amount, payload_override=override
            )
        else:
            receipt = self.audit(
                action, contract_address, amount, payload_override=override
            )

        audit = receipt.get("audit") or {}
        status = str(audit.get("status", "")).upper()
        if status == "REJECTED":
            raise XapsRejectedError(
                str(audit.get("beta_attack") or audit.get("reason") or "REJECTED"),
                receipt=receipt,
            )

        sink = self.query_sink(query, receipt, oracle_url=oracle_url)
        return {"receipt": receipt, "sink": sink, "query": query}

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

try:
    from loguru import logger
except Exception:
    import warnings
    logger = type("logger", (), {"warning": lambda *a, **k: warnings.warn(str(a[0]) if a else "", UserWarning)})()

def _receipt_status(receipt: dict) -> str:
    """Status is signed at mint time; API may nest it under audit."""
    if receipt.get("status"):
        return str(receipt["status"])
    audit = receipt.get("audit") or {}
    if isinstance(audit, dict) and audit.get("status"):
        return str(audit["status"])
    return ""


def _canonical_receipt_message_for_verify(receipt: dict) -> str:
    """Stable JSON canonicalization used for ECDSA verification.
    (HMAC path uses the original colon string inside verify_receipt_hmac for legacy compatibility.)
    """
    return json.dumps({
        "receipt_id": receipt["receipt_id"],
        "agent_key": receipt["agent_key"],
        "payload_hash": receipt["payload_hash"],
        "status": _receipt_status(receipt),
        "signed_at": receipt["signed_at"],
    }, sort_keys=True, separators=(',', ':'))


def verify_receipt_ecdsa(receipt: dict, public_key_hex: str) -> bool:
    """
    Verify an ECDSA (NIST256p) signed Xaps receipt.
    Returns False on any error (never raises).
    """
    try:
        from ecdsa import VerifyingKey, NIST256p, BadSignatureError
    except ImportError:
        try:
            from ecdsa import VerifyingKey, NIST256p  # type: ignore
            from ecdsa.keys import BadSignatureError  # type: ignore
        except ImportError:
            logger.warning(
                "ecdsa package not installed — cannot verify ECDSA receipts. "
                "pip install ecdsa"
            )
            return False
    try:
        vk = VerifyingKey.from_string(
            bytes.fromhex(public_key_hex),
            curve=NIST256p,
            hashfunc=hashlib.sha256,
        )
        sig = bytes.fromhex(receipt["signature"])
        message = _canonical_receipt_message_for_verify(receipt)
        vk.verify(sig, message.encode(), hashfunc=hashlib.sha256)
        return True
    except Exception:
        # BadSignatureError, ValueError, KeyError, malformed hex, etc.
        return False


def verify_receipt_hmac(receipt: dict, secret: str) -> bool:
    """
    Verify an HMAC-signed receipt using the node's shared secret.
    ⚠️ Only parties who know the secret (node operator) can do this.
    Returns False on error.
    """
    try:
        status = _receipt_status(receipt)
        message = (
            f"{receipt['receipt_id']}:{receipt['agent_key']}:"
            f"{receipt['payload_hash']}:{status}:{receipt['signed_at']}"
        )
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


RECEIPT_HEADER = "X-XAPS-Receipt"


def independent_clearance(
    receipt_id: str,
    *,
    require_use_case: str = "value_move",
    amount: float | None = None,
    pay_to: str | None = None,
    resource: str | None = None,
    payload_hash: str | None = None,
    base_url: str = DEFAULT_BASE_URL,
    timeout: float = 10.0,
) -> dict[str, Any]:
    """Ask the Tollbooth — not the payer — whether this receipt is cleared.

    Pass ``amount`` / ``pay_to`` / ``resource`` to bind the receipt to *this*
    payment (replay protection). Facilitators should always send them.
    """
    rid = (receipt_id or "").strip()
    if not rid:
        raise XapsAPIError("receipt_id required")
    url = base_url.rstrip("/")
    body: dict[str, Any] = {"receipt_id": rid, "require_use_case": require_use_case}
    if amount is not None:
        body["amount"] = amount
    if pay_to:
        body["pay_to"] = pay_to
    if resource:
        body["resource"] = resource
    if payload_hash:
        body["payload_hash"] = payload_hash
    try:
        with httpx.Client(timeout=timeout, headers={"User-Agent": "xaps-sdk/clearance"}) as c:
            r = c.post(f"{url}/receipts/clear", json=body)
            if r.status_code == 404:
                raise XapsAPIError("Unknown receipt_id")
            if r.status_code >= 400:
                raise XapsAPIError(f"API error {r.status_code}: {r.text[:200]}")
            return r.json()
    except httpx.HTTPError as visc:
        raise XapsAPIError(f"Connection failed: {visc}") from visc


def require_value_clearance(receipt_id: str, **kwargs: Any) -> dict[str, Any]:
    """Fail closed unless cleared for this value_move (and binding if given)."""
    view = independent_clearance(receipt_id, require_use_case="value_move", **kwargs)
    if not view.get("clear"):
        raise XapsRejectedError(view.get("reason") or "not cleared for value_move", receipt=view)
    return view

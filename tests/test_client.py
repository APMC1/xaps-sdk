import pytest
from unittest.mock import MagicMock, patch

from xaps import (
    XapsClient,
    XapsAuthError,
    XapsPaymentError,
    XapsAPIError,
    __version__,
    is_fast_allowlisted,
)


def test_version():
    assert __version__ == "0.1.3"


def test_missing_key():
    with patch.dict("os.environ", {}, clear=True):
        with pytest.raises(ValueError):
            XapsClient()


def test_audit_ok():
    resp = MagicMock(status_code=200)
    resp.json.return_value = {"audit": {"status": "APPROVED"}, "remaining_balance": 9.0}
    with patch("httpx.Client") as MockClient:
        MockClient.return_value.post.return_value = resp
        r = XapsClient(api_key="k", base_url="https://api.test").audit("a", "0x1", 1.0)
    assert r["audit"]["status"] == "APPROVED"


def test_is_fast_allowlisted():
    assert is_fast_allowlisted("fast_reason")
    assert not is_fast_allowlisted("wire_transfer")


def test_audit_fast_hits_fast_endpoint():
    resp = MagicMock(status_code=200)
    resp.json.return_value = {"audit": {"status": "APPROVED", "path": "fast_approve"}}
    with patch("httpx.Client") as MockClient:
        inst = MockClient.return_value
        inst.post.return_value = resp
        r = XapsClient(api_key="k", base_url="https://api.test").audit_fast(
            "fast_reason", "", 0.01
        )
    inst.post.assert_called_once()
    assert inst.post.call_args[0][0] == "/verify/fast"
    assert r["audit"]["path"] == "fast_approve"


def test_audit_auto_routes_fast():
    resp = MagicMock(status_code=200)
    resp.json.return_value = {"audit": {"status": "APPROVED", "path": "fast_approve"}}
    with patch("httpx.Client") as MockClient:
        inst = MockClient.return_value
        inst.post.return_value = resp
        XapsClient(api_key="k", base_url="https://api.test").audit_auto("fast_reason", "", 0.01)
    assert inst.post.call_args[0][0] == "/verify/fast"


def test_build_payload_merges_override():
    payload = XapsClient._build_payload(
        "fast_reason", "", 0.01, payload_override={"extra": "field"}
    )
    assert payload == {
        "action": "fast_reason",
        "contract_address": "",
        "amount": 0.01,
        "extra": "field",
    }


def test_401():
    resp = MagicMock(status_code=401, text="unauthorized")
    with patch("httpx.Client") as MockClient:
        MockClient.return_value.post.return_value = resp
        with pytest.raises(XapsAuthError):
            XapsClient(api_key="k", base_url="https://api.test").audit("a", "0x1", 1.0)


def test_query_sink_posts_receipt():
    sink_resp = MagicMock(status_code=200)
    sink_resp.json.return_value = {
        "data": {"full_name": "o/r", "stars": 1},
        "provenance": {"type": "github_repo"},
        "verify_status": "VERIFIED",
    }
    receipt = {"audit": {"status": "APPROVED"}, "receipt_id": "r1"}
    with patch("httpx.post", return_value=sink_resp) as post:
        out = XapsClient(api_key="k", base_url="https://api.test").query_sink(
            "github repo o/r",
            receipt,
            oracle_url="http://sink.test",
        )
    assert out["data"]["full_name"] == "o/r"
    assert post.call_args[0][0] == "http://sink.test/oracle/query"
    assert post.call_args[1]["json"]["receipt"] == receipt


def test_audit_then_query_chains():
    toll = MagicMock(status_code=200)
    toll.json.return_value = {
        "audit": {"status": "APPROVED", "path": "fast_approve"},
        "receipt_id": "r2",
    }
    sink = MagicMock(status_code=200)
    sink.json.return_value = {"data": {"items": []}, "provenance": {"type": "github_search"}}

    with patch("httpx.Client") as MockClient:
        MockClient.return_value.post.return_value = toll
        with patch("httpx.post", return_value=sink):
            result = XapsClient(api_key="k", base_url="https://api.test").audit_then_query(
                "search github agents",
                oracle_url="http://sink.test",
                use_fast=True,
            )
    assert result["query"] == "search github agents"
    assert result["receipt"]["receipt_id"] == "r2"
    assert "sink" in result


def test_register_creates_client():
    resp = MagicMock(status_code=200)
    resp.json.return_value = {
        "status": "ok",
        "agent_key": "xaps_new_agent_key",
        "balance_usd": 0.0,
    }
    with patch("httpx.post", return_value=resp) as mock_post:
        client, meta = XapsClient.register(base_url="https://api.test")
    mock_post.assert_called_once()
    assert client.api_key == "xaps_new_agent_key"
    assert meta["balance_usd"] == 0.0


def test_get_balance():
    resp = MagicMock(status_code=200)
    resp.json.return_value = {"status": "ok", "balance_usd": 42.5}
    with patch("httpx.Client") as MockClient:
        inst = MockClient.return_value
        inst.get.return_value = resp
        balance = XapsClient(api_key="k", base_url="https://api.test").get_balance()
    assert balance == 42.5
    inst.get.assert_called_once_with("/agents/balance")


def test_bootstrap_registers_when_no_env():
    reg = MagicMock(status_code=200)
    reg.json.return_value = {
        "status": "ok",
        "agent_key": "xaps_bootstrapped",
        "balance_usd": 1.0,
    }
    fund = MagicMock(status_code=200)
    fund.json.return_value = {
        "status": "ok",
        "agent_key": "xaps_bootstrapped",
        "balance_usd": 1.0,
        "rails": [],
    }
    with patch.dict("os.environ", {}, clear=True):
        with patch("httpx.post", return_value=reg):
            with patch("httpx.Client") as MockClient:
                inst = MockClient.return_value
                inst.get.return_value = fund
                client, info = XapsClient.bootstrap(base_url="https://api.test")
    assert client.api_key == "xaps_bootstrapped"
    assert info["reused_key"] is False


def test_create_checkout():
    resp = MagicMock(status_code=200)
    resp.json.return_value = {
        "status": "ok",
        "checkout_url": "https://checkout.stripe.com/test",
        "session_id": "cs_test",
    }
    with patch("httpx.Client") as MockClient:
        inst = MockClient.return_value
        inst.post.return_value = resp
        body = XapsClient(api_key="k", base_url="https://api.test").create_checkout(25.0)
    inst.post.assert_called_once()
    assert body["checkout_url"].startswith("https://checkout.stripe.com/")


@pytest.mark.asyncio
async def test_audit_async():
    resp = MagicMock(status_code=200)
    resp.json.return_value = {"audit": {"status": "APPROVED"}}
    with patch("httpx.AsyncClient") as MockAsync:
        inst = MockAsync.return_value

        async def post(*a, **kw):
            return resp

        async def aclose():
            return None

        inst.post = post
        inst.aclose = aclose
        c = XapsClient(api_key="k", base_url="https://api.test")
        r = await c.audit_async("a", "0x1", 1.0)
        await c.aclose()
    assert r["audit"]["status"] == "APPROVED"
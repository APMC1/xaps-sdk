import pytest
from unittest.mock import MagicMock, patch

from xaps import (
    XapsClient,
    XapsAuthError,
    XapsPaymentError,
    XapsAPIError,
    __version__,
)


def test_version():
    assert __version__ == "0.1.2"


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


def test_401():
    resp = MagicMock(status_code=401, text="unauthorized")
    with patch("httpx.Client") as MockClient:
        MockClient.return_value.post.return_value = resp
        with pytest.raises(XapsAuthError):
            XapsClient(api_key="k", base_url="https://api.test").audit("a", "0x1", 1.0)


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
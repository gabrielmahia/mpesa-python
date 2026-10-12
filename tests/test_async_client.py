"""Offline regression tests for the genuine aiohttp transport (no Safaricom calls)."""
import asyncio
import base64
from unittest.mock import patch

import pytest

pytest.importorskip("aiohttp")

from mpesa import MpesaAsyncClient
from mpesa.exceptions import AuthenticationError, MpesaError, ValidationError
from mpesa.exceptions import TimeoutError as MpesaTimeoutError


def client():
    return MpesaAsyncClient("test-key", "test-secret", "174379", passkey="pass", sandbox=True)


def test_async_stk_parity_phone_party_b_and_password(monkeypatch):
    calls = []

    async def fake_post(self, path, payload):
        calls.append((path, payload))
        return {"MerchantRequestID": "m", "CheckoutRequestID": "c", "ResponseDescription": "ok"}

    monkeypatch.setattr(MpesaAsyncClient, "_post", fake_post)

    async def exercise():
        async with client() as c:
            result = await c.stk_push(
                "0112345678", 100, "Invoice-1",
                callback_url="https://example.com/payments/stk/callback",
                transaction_type="CustomerBuyGoodsOnline", party_b="654321",
            )
            assert result.checkout_request_id == "c"
    asyncio.run(exercise())
    path, payload = calls[0]
    assert path == "/mpesa/stkpush/v1/processrequest"
    assert payload["PartyA"] == payload["PhoneNumber"] == "254112345678"
    assert payload["BusinessShortCode"] == "174379"
    assert payload["PartyB"] == "654321"
    assert payload["TransactionType"] == "CustomerBuyGoodsOnline"
    assert base64.b64decode(payload["Password"]).decode() == "174379pass" + payload["Timestamp"]


def test_async_validation_before_network(monkeypatch):
    calls = []

    async def fail_post(self, path, payload):
        calls.append(path)
        raise AssertionError("Invalid payload reached network")

    monkeypatch.setattr(MpesaAsyncClient, "_post", fail_post)

    async def exercise():
        c = client()
        with pytest.raises(ValidationError):
            await c.stk_push("bad", 20, "invoice")
        with pytest.raises(ValidationError):
            await c.stk_push("0712345678", 20, "invoice", party_b="12")
        await c.aclose()

    asyncio.run(exercise())
    assert not calls


def test_async_query_b2c_other_apis_and_callback_parity(monkeypatch):
    requests = []

    async def fake_post(self, path, payload):
        requests.append((path, payload))
        if "stkpushquery" in path:
            return {"ResultCode": 0, "CheckoutRequestID": "c"}
        if "b2c" in path:
            return {"ResponseCode": "0", "ConversationID": "c2"}
        return {"ResponseCode": "0"}

    monkeypatch.setattr(MpesaAsyncClient, "_post", fake_post)

    async def exercise():
        async with client() as c:
            result = await c.stk_query("c")
            assert result.is_paid and result.result_code == "0"
            result_b2c = await c.b2c("0712345678", 100, callback_url="https://e.com/payments/b2c")
            assert result_b2c.conversation_id == "c2"
            await c.c2b_register_urls("https://e.com/payments/validate", "https://e.com/payments/confirm")
            await c.account_balance("https://e.com/payments/balance")
            assert c.parse_stk_callback({"Body": {"stkCallback": {
                "ResultCode": 1032, "CheckoutRequestID": "c"
            }}})["paid"] is False

    asyncio.run(exercise())
    assert [r[0] for r in requests] == [
        "/mpesa/stkpushquery/v1/query", "/mpesa/b2c/v3/paymentrequest",
        "/mpesa/c2b/v1/registerurl", "/mpesa/accountbalance/v1/query"
    ]


class FakeResponse:
    def __init__(self, status, data=None, raw=None):
        self.status = status
        self.data = data if data is not None else {}
        self.raw = raw if raw is not None else "{}"

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    async def json(self, content_type=None):
        await asyncio.sleep(0)
        return self.data

    async def text(self):
        await asyncio.sleep(0)
        return self.raw


class FakeSession:
    closed = False

    def __init__(self, token_response=None, post_response=None):
        self.get_calls = []
        self.post_calls = []
        self.token_response = token_response or FakeResponse(
            200, {"access_token": "TEST_TOKEN", "expires_in": "3600"}
        )
        self.post_response = post_response or FakeResponse(200, raw='{"ResponseCode":"0"}')

    def get(self, url, **kwargs):
        self.get_calls.append((url, kwargs))
        return self.token_response

    def post(self, url, **kwargs):
        self.post_calls.append((url, kwargs))
        return self.post_response

    async def close(self):
        self.closed = True


def test_auth_lock_token_cache_transport_and_close(monkeypatch):
    fake = FakeSession()

    async def exercise():
        c = client()
        monkeypatch.setattr(c, "_http", lambda: fake)
        tokens = await asyncio.gather(*[c._token() for _ in range(8)])
        assert tokens == ["TEST_TOKEN"] * 8
        assert len(fake.get_calls) == 1
        assert fake.get_calls[0][1]["auth"].login == "test-key"
        await asyncio.gather(c.account_balance("https://example.com/payments/cb"),
                             c.c2b_register_urls("https://example.com/payments/v",
                                                 "https://example.com/payments/c"))
        assert len(fake.post_calls) == 2
        assert all(post[1]["headers"]["Authorization"] == "Bearer TEST_TOKEN"
                   for post in fake.post_calls)
        await c.aclose()
    asyncio.run(exercise())


def test_http_error_and_auth_error(monkeypatch):
    async def exercise():
        c = client()
        fake = FakeSession(post_response=FakeResponse(400, raw='{"errorMessage":"Bad request","errorCode":"X1"}'))
        monkeypatch.setattr(c, "_http", lambda: fake)
        with pytest.raises(MpesaError) as caught:
            await c.account_balance("https://example.com/payments/cb")
        assert caught.value.code == "X1"

        c2 = client()
        monkeypatch.setattr(c2, "_http", lambda: FakeSession(token_response=FakeResponse(401, raw="unauthorized")))
        with pytest.raises(AuthenticationError):
            await c2._token()
    asyncio.run(exercise())


def test_post_timeout_is_explicit(monkeypatch):
    class TimedOut(FakeSession):
        def post(self, url, **kwargs):
            raise asyncio.TimeoutError()

    async def exercise():
        c = client()
        monkeypatch.setattr(c, "_http", lambda: TimedOut())
        with pytest.raises(MpesaTimeoutError):
            await c.account_balance("https://example.com/payments/cb")
    asyncio.run(exercise())


def test_base_url_validation_matches_sync_client():
    with pytest.raises(ValueError):
        MpesaAsyncClient("k", "s", "174379", base_url="http://remote.example")

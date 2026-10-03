"""STK Push request-body tests.

Added after production feedback (PR #2) showed that nothing asserted what is sent to Daraja: the suite checked
instantiation and validation only, so a hardcoded PartyB could never have failed a test. These tests capture the
payload at the HTTP boundary (no network)."""
import base64

import pytest

from mpesa.client import MpesaClient
from mpesa.exceptions import ValidationError

SHORTCODE = "174379"
TILL = "654321"


def make_client() -> MpesaClient:
    return MpesaClient(consumer_key="k", consumer_secret="s", shortcode=SHORTCODE, passkey="pk", sandbox=True)


@pytest.fixture
def calls(monkeypatch):
    seen: list[tuple[str, dict]] = []

    def fake_post(self, path, payload):
        seen.append((path, payload))
        return {"MerchantRequestID": "m1", "CheckoutRequestID": "c1", "ResponseDescription": "ok", "CustomerMessage": "ok"}

    monkeypatch.setattr(MpesaClient, "_post", fake_post)
    return seen


def push(**kw):
    return make_client().stk_push("0712345678", 10, "ref", callback_url="https://example.com/cb", **kw)


def test_paybill_default_sends_party_b_equal_to_shortcode(calls):
    push()
    payload = calls[0][1]
    assert payload["BusinessShortCode"] == SHORTCODE and payload["PartyB"] == SHORTCODE
    assert payload["TransactionType"] == "CustomerPayBillOnline"


def test_explicit_none_falls_back_to_shortcode(calls):
    push(party_b=None)
    assert calls[0][1]["PartyB"] == SHORTCODE


def test_buy_goods_party_b_override_reaches_the_till(calls):
    push(transaction_type="CustomerBuyGoodsOnline", party_b=TILL)
    payload = calls[0][1]
    assert payload["PartyB"] == TILL
    assert payload["BusinessShortCode"] == SHORTCODE          # the shortcode (head office/store) is unchanged
    assert payload["TransactionType"] == "CustomerBuyGoodsOnline"


def test_party_b_does_not_change_the_password_or_the_customer_fields(calls):
    push(party_b=TILL)
    payload = calls[0][1]
    assert base64.b64decode(payload["Password"]).decode() == f"{SHORTCODE}pk{payload['Timestamp']}"
    assert payload["PartyA"] == payload["PhoneNumber"] == "254712345678"


def test_party_b_accepts_an_int_and_sends_a_string(calls):
    push(party_b=int(TILL))
    assert calls[0][1]["PartyB"] == TILL


def test_invalid_party_b_is_rejected_before_any_network_call(calls):
    with pytest.raises(ValidationError) as exc:
        push(party_b="12")
    assert exc.value.code == "INVALID_SHORTCODE"
    assert calls == []

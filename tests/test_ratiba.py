"""Ratiba (standing order) tests: payload at the HTTP boundary, schedule maths, local validation. No network."""
import asyncio
from datetime import date, timedelta

import pytest

from mpesa import RatibaResult
from mpesa.client import MpesaClient
from mpesa.exceptions import ValidationError
from mpesa.ratiba import PATH, build, count_payments

SHORTCODE = "174379"
CB = "https://example.com/ratiba/cb"
TOMORROW = date.today() + timedelta(days=1)
OK = {"ResponseHeader": {"responseRefID": "ref-1", "responseCode": "200", "responseDescription": "Request accepted for processing"},
      "ResponseBody": {"responseDescription": "Request accepted for processing", "responseCode": "200"}}


def client() -> MpesaClient:
    return MpesaClient(consumer_key="k", consumer_secret="s", shortcode=SHORTCODE, sandbox=True)


@pytest.fixture
def calls(monkeypatch):
    seen = []

    def fake_post(self, path, payload):
        seen.append((path, payload))
        return OK

    monkeypatch.setattr(MpesaClient, "_post", fake_post)
    return seen


def create(**kw):
    args = dict(phone="0712345678", amount=500, standing_order_name="Loan 42", start_date=TOMORROW,
                end_date=TOMORROW + timedelta(days=364), account_reference="LN42", callback_url=CB)
    args.update(kw)
    return client().ratiba_create(**args)


def test_payload_matches_daraja_contract(calls):
    r = create()
    path, p = calls[0]
    assert path == PATH == "/standingorder/v1/createStandingOrderExternal"
    assert p == {
        "StandingOrderName": "Loan 42", "StartDate": TOMORROW.strftime("%Y%m%d"),
        "EndDate": (TOMORROW + timedelta(days=364)).strftime("%Y%m%d"), "BusinessShortCode": SHORTCODE,
        "TransactionType": "Standing Order Customer Pay Bill", "ReceiverPartyIdentifierType": "4",
        "Amount": "500", "PartyA": "254712345678", "CallBackURL": CB, "AccountReference": "LN42",
        "TransactionDesc": "Standing orde", "Frequency": "4",
    }
    assert isinstance(r, RatibaResult) and r.accepted and r.response_ref_id == "ref-1"
    assert r.schedule.payments == 12 and r.schedule.total_commitment_kes == 6000


def test_till_receiver_and_frequency_codes(calls):
    create(receiver_type="till", frequency="3")
    p = calls[0][1]
    assert (p["TransactionType"], p["ReceiverPartyIdentifierType"], p["Frequency"]) == ("Standing Order Customer Pay Marchant", "2", "3")


def test_iso_string_dates_and_names_accepted(calls):
    r = create(start_date=TOMORROW.isoformat(), end_date=TOMORROW.strftime("%Y%m%d"), frequency="one-off")
    assert r.schedule.payments == 1 and calls[0][1]["Frequency"] == "1"


def test_bi_monthly_has_no_invented_count(calls):
    r = create(frequency="bi_monthly")
    assert r.schedule.payments is None and r.schedule.total_commitment_kes is None


def test_rejected_response_is_not_accepted(monkeypatch):
    monkeypatch.setattr(MpesaClient, "_post", lambda self, path, payload: {"ResponseHeader": {"responseCode": "500", "responseDescription": "Duplicate"}})
    r = create()
    assert not r.accepted and r.response_description == "Duplicate"


@pytest.mark.parametrize("kw", [
    {"frequency": "fortnightly"}, {"receiver_type": "bank"}, {"amount": 0}, {"amount": 150_001},
    {"phone": "12345"}, {"standing_order_name": ""}, {"standing_order_name": "x" * 61},
    {"account_reference": "!!"}, {"callback_url": "http://example.com"},
    {"start_date": date.today() - timedelta(days=1)}, {"start_date": "2026-02-30"}, {"start_date": "tomorrow"},
    {"end_date": TOMORROW - timedelta(days=1)},
])
def test_invalid_input_rejected_before_network(monkeypatch, kw):
    def boom(*a, **k):
        raise AssertionError("network call made")
    monkeypatch.setattr(MpesaClient, "_post", boom)
    with pytest.raises(ValidationError):
        create(**kw)


@pytest.mark.parametrize("freq,end_offset,expected", [
    ("daily", 6, 7), ("weekly", 27, 4), ("monthly", 0, 1), ("quarterly", 364, 4), ("half_year", 365, 3), ("yearly", 731, 3),
])
def test_count_payments(freq, end_offset, expected):
    start = date(2027, 1, 1)
    assert count_payments(start, start + timedelta(days=end_offset), freq) == expected


def test_month_end_clamps():
    assert count_payments(date(2027, 1, 31), date(2027, 3, 31), "monthly") == 3  # Jan 31, Feb 28, Mar 31


def test_build_uses_injected_today():
    with pytest.raises(ValidationError):
        build(shortcode=SHORTCODE, phone="0712345678", amount=1, standing_order_name="n", start_date="2027-01-01",
              end_date="2027-01-01", account_reference="r", callback_url=CB, today=date(2027, 1, 2))


def test_async_parity(monkeypatch):
    pytest.importorskip("aiohttp")
    from mpesa.async_client import MpesaAsyncClient
    seen = []

    async def fake_post(self, path, payload):
        seen.append((path, payload))
        return OK
    monkeypatch.setattr(MpesaAsyncClient, "_post", fake_post)
    sync_calls = []
    monkeypatch.setattr(MpesaClient, "_post", lambda self, path, payload: sync_calls.append((path, payload)) or OK)
    create()

    async def go():
        async with MpesaAsyncClient(consumer_key="k", consumer_secret="s", shortcode=SHORTCODE, sandbox=True) as c:
            return await c.ratiba_create(phone="0712345678", amount=500, standing_order_name="Loan 42", start_date=TOMORROW,
                                         end_date=TOMORROW + timedelta(days=364), account_reference="LN42", callback_url=CB)
    r = asyncio.run(go())
    assert seen == sync_calls and r.accepted and r.schedule.payments == 12

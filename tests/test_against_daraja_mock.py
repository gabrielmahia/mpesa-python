"""The real SDK against daraja-mock: no Safaricom account, key or network needed. Also pins base_url validation, because the client sends the consumer secret to the host it is given."""
import socket

import pytest
from daraja_mock import DarajaMock

from mpesa import MpesaClient
from mpesa.exceptions import MpesaError


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def mock_and_url():
    mock = DarajaMock()
    return mock, mock.run_thread(port=_free_port())


def _client(url):
    return MpesaClient("k", "s", "174379", passkey="p", sandbox=True, base_url=url)


def test_stk_push_and_query_round_trip_through_the_mock(mock_and_url):
    mock, url = mock_and_url
    mock.reset()
    r = _client(url).stk_push("0712345678", 10, "REF1", "Test", callback_url="https://example.com/cb")
    assert r.checkout_request_id
    body = [e for e in mock.request_log() if e["path"].endswith("/stkpush/v1/processrequest")][-1]["body"]
    assert str(body["PhoneNumber"]) == "254712345678" and str(body["Amount"]) == "10"
    q = _client(url).stk_query(r.checkout_request_id)
    assert q.result_code == "0"  # a string, as in Safaricom's JSON


def test_a_configured_cancellation_is_reported(mock_and_url):
    mock, url = mock_and_url
    mock.reset()
    mock.set_stk_result(1032)
    q = _client(url).stk_query("ws_CO_X")
    assert q.result_code == "1032"


def test_base_url_wins_over_the_sandbox_flag(mock_and_url):
    _, url = mock_and_url
    assert _client(url)._base == url


@pytest.mark.parametrize("bad", ["http://evil.example", "ftp://localhost", "localhost:8080", "https://", ""])
def test_unsafe_base_urls_are_rejected(bad):
    with pytest.raises(ValueError):
        MpesaClient("k", "s", "174379", base_url=bad)


@pytest.mark.parametrize("ok", ["https://sandbox.example.com", "http://localhost:9000", "http://127.0.0.1:9000/"])
def test_https_or_localhost_http_is_accepted(ok):
    assert MpesaClient("k", "s", "174379", base_url=ok)._base == ok.rstrip("/")


def test_default_behaviour_is_unchanged():
    assert MpesaClient("k", "s", "174379")._base == "https://sandbox.safaricom.co.ke"
    assert MpesaClient("k", "s", "174379", sandbox=False)._base == "https://api.safaricom.co.ke"


def test_an_unreachable_base_url_raises_a_clear_error():
    with pytest.raises(MpesaError):
        MpesaClient("k", "s", "174379", base_url=f"http://127.0.0.1:{_free_port()}", timeout=2).stk_query("ws_CO_X")

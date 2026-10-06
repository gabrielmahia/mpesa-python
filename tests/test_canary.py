"""The canary's logic, exercised against daraja-mock so it is verified before it ever touches Safaricom."""
import importlib.util
import json
import pathlib
import socket

import pytest
from daraja_mock import DarajaMock

_spec = importlib.util.spec_from_file_location("sandbox_canary", pathlib.Path(__file__).resolve().parents[1] / "scripts" / "sandbox_canary.py")
canary = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(canary)


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def mock_url():
    return DarajaMock().run_thread(port=_free_port())


@pytest.fixture
def creds(monkeypatch):
    monkeypatch.setenv("DARAJA_CONSUMER_KEY", "k" * 48)
    monkeypatch.setenv("DARAJA_CONSUMER_SECRET", "s" * 64)


def test_healthy_against_the_mock(mock_url, creds, capsys):
    assert canary.main(["--base-url", mock_url, "--wait", "0"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["canary"] == "healthy" and out["oauth"] == "ok" and out["stk_push"] == "ok" and out["stk_query"].startswith("ok")


def test_a_failing_host_is_reported_as_broken_not_healthy(creds, capsys):
    assert canary.main(["--base-url", f"http://127.0.0.1:{_free_port()}", "--wait", "0"]) == 1
    assert json.loads(capsys.readouterr().out)["canary"] == "BROKEN"


def test_missing_credentials_refuse_by_default(monkeypatch, capsys):
    monkeypatch.delenv("DARAJA_CONSUMER_KEY", raising=False)
    monkeypatch.delenv("DARAJA_CONSUMER_SECRET", raising=False)
    assert canary.main([]) == 2
    assert "docs/SANDBOX_SETUP.md" in capsys.readouterr().err


def test_missing_credentials_skip_cleanly_when_asked(monkeypatch, capsys):
    monkeypatch.delenv("DARAJA_CONSUMER_KEY", raising=False)
    monkeypatch.delenv("DARAJA_CONSUMER_SECRET", raising=False)
    assert canary.main(["--skip-if-no-credentials"]) == 0
    assert json.loads(capsys.readouterr().out)["canary"] == "skipped"


def test_the_secret_is_never_printed(mock_url, creds, capsys):
    canary.main(["--base-url", mock_url, "--wait", "0"])
    captured = capsys.readouterr()
    assert "s" * 64 not in captured.out + captured.err and "k" * 48 not in captured.out + captured.err


def test_a_transient_status_query_500_is_retried_not_reported_as_broken(creds, capsys, monkeypatch):
    """The live sandbox's STK query is intermittently 500; the first live canary run reported BROKEN on a single such error."""
    from mpesa import MpesaClient
    from mpesa.exceptions import MpesaError

    real, calls = MpesaClient.stk_query, {"n": 0}

    def flaky(self, checkout_request_id):
        calls["n"] += 1
        if calls["n"] < 3:
            raise MpesaError("API error 500: transient")
        return real(self, checkout_request_id)

    monkeypatch.setattr(MpesaClient, "stk_query", flaky)
    url = DarajaMock().run_thread(port=_free_port())
    assert canary.main(["--base-url", url, "--wait", "0", "--retry-wait", "0"]) == 0
    assert "attempt 3" in json.loads(capsys.readouterr().out.strip().splitlines()[-1])["stk_query"]


def test_a_persistent_status_query_failure_is_still_broken(creds, capsys, monkeypatch):
    from mpesa import MpesaClient
    from mpesa.exceptions import MpesaError

    def always(self, checkout_request_id):
        raise MpesaError("API error 500: down")

    monkeypatch.setattr(MpesaClient, "stk_query", always)
    url = DarajaMock().run_thread(port=_free_port())
    assert canary.main(["--base-url", url, "--wait", "0", "--retry-wait", "0"]) == 1
    assert "FAILED" in json.loads(capsys.readouterr().out.strip().splitlines()[-1])["stk_query"]

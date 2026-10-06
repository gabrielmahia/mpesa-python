"""The probe's logic against daraja-mock, which implements B2C v3 only: v3 must read ACCEPTED and v1 ENDPOINT NOT FOUND."""
import importlib.util
import json
import pathlib
import socket

import pytest
from daraja_mock import DarajaMock

_spec = importlib.util.spec_from_file_location("sandbox_probe", pathlib.Path(__file__).resolve().parents[1] / "scripts" / "sandbox_probe.py")
probe = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(probe)


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def mock_url():
    return DarajaMock().run_thread(port=_free_port())


@pytest.fixture
def env(monkeypatch):
    for k, v in {"DARAJA_CONSUMER_KEY": "k" * 48, "DARAJA_CONSUMER_SECRET": "s" * 64, "DARAJA_INITIATOR_NAME": "testapi", "DARAJA_SECURITY_CREDENTIAL": "CRED" * 20}.items():
        monkeypatch.setenv(k, v)


def test_v3_is_accepted_and_the_missing_v1_is_reported_as_not_found(mock_url, env, capsys):
    assert probe.main(["b2c", "--base-url", mock_url]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["v3"] == "ACCEPTED" and out["v1"] == "ENDPOINT NOT FOUND"


def test_missing_security_credential_skips_with_instructions(monkeypatch, capsys):
    monkeypatch.setenv("DARAJA_CONSUMER_KEY", "k" * 48)
    monkeypatch.setenv("DARAJA_CONSUMER_SECRET", "s" * 64)
    monkeypatch.delenv("DARAJA_SECURITY_CREDENTIAL", raising=False)
    assert probe.main(["b2c"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["result"] == "SKIPPED" and "M-Pesa Sandbox" in out["reason"]


def test_initiator_and_shortcode_default_and_are_reported(mock_url, monkeypatch, capsys):
    """The portal page may have no initiator or shortcode field: default to the documented sandbox initiator and a placeholder shortcode, and say so."""
    for k, v in {"DARAJA_CONSUMER_KEY": "k" * 48, "DARAJA_CONSUMER_SECRET": "s" * 64, "DARAJA_SECURITY_CREDENTIAL": "CRED" * 20}.items():
        monkeypatch.setenv(k, v)
    monkeypatch.delenv("DARAJA_INITIATOR_NAME", raising=False)
    monkeypatch.delenv("DARAJA_B2C_SHORTCODE", raising=False)
    assert probe.main(["b2c", "--base-url", mock_url]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["initiator"] == "testapi" and out["shortcode"] == "600000" and out["v3"] == "ACCEPTED"


def test_an_unreachable_host_fails_at_oauth_not_silently(env, capsys):
    assert probe.main(["b2c", "--base-url", f"http://127.0.0.1:{_free_port()}"]) == 1
    assert json.loads(capsys.readouterr().out)["step"] == "oauth"


def test_no_credentials_refuses(monkeypatch):
    monkeypatch.delenv("DARAJA_CONSUMER_KEY", raising=False)
    assert probe.main(["b2c"]) == 2


def test_secrets_are_never_printed(mock_url, env, capsys):
    probe.main(["b2c", "--base-url", mock_url])
    c = capsys.readouterr()
    assert not any(s in c.out + c.err for s in ("s" * 64, "k" * 48, "CRED" * 20))


@pytest.mark.parametrize("status,body,expected", [(200, '{"ResponseCode":"0"}', "ACCEPTED"), (404, "", "ENDPOINT NOT FOUND"), (400, '{"errorMessage":"Bad Request"}', "REJECTED (400: Bad Request)")])
def test_classification(status, body, expected):
    assert probe.classify(status, body) == expected

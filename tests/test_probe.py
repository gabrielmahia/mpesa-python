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


def _stub_server(responses):
    """A tiny HTTP stub: daraja-mock has no C2B endpoints, so the C2B probe is tested against this."""
    import http.server
    import threading

    class H(http.server.BaseHTTPRequestHandler):
        def _send(self, status, body):
            data = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):  # OAuth
            self._send(200, {"access_token": "tok", "expires_in": "3599"})

        def do_POST(self):
            self.rfile.read(int(self.headers.get("Content-Length", 0)))
            status, body = responses.get(self.path, (404, {}))
            self._send(status, body)

        def log_message(self, *a):
            pass

    srv = http.server.HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{srv.server_port}"


def test_c2b_uses_the_first_shortcode_that_accepts_registerurl_and_simulates(env, capsys):
    ok = (200, {"ResponseCode": "0", "ResponseDescription": "Success"})
    url = _stub_server({"/mpesa/c2b/v2/registerurl": ok, "/mpesa/c2b/v2/simulate": ok})
    assert probe.main(["c2b", "--base-url", url]) == 0
    out = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    first = next(iter(out["shortcodes_tried"].values()))
    assert first == {"registerurl": "ACCEPTED", "simulate": "ACCEPTED"} and len(out["shortcodes_tried"]) == 1


def test_c2b_moves_on_when_a_shortcode_is_rejected_and_reports_each(env, capsys):
    url = _stub_server({"/mpesa/c2b/v2/registerurl": (400, {"errorMessage": "Invalid ShortCode"})})
    assert probe.main(["c2b", "--base-url", url]) == 0
    out = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert len(out["shortcodes_tried"]) == 5 and all("REJECTED" in v["registerurl"] for v in out["shortcodes_tried"].values())


def test_c2b_refuses_without_credentials(monkeypatch):
    monkeypatch.delenv("DARAJA_CONSUMER_KEY", raising=False)
    assert probe.main(["c2b"]) == 2


@pytest.mark.parametrize("status,body,expected", [
    (404, "", "NOT FOUND"),
    (401, "Error Occurred - Invalid Access Token - Invalid API call as no apiproduct match found", "PRODUCT NOT GRANTED"),
    (401, "Error Occurred - Invalid Access Token - ", "UNAUTHORIZED (no product detail)"),
    (403, '<html style="height:100%"><head><META NAME="ROBOTS"', "EDGE BLOCK (403, HTML page)"),
    (403, '{"errorMessage":"x"}', "FORBIDDEN"),
    (400, '{"errorCode":"400.002.02"}', "REACHABLE (400)"),
])
def test_reach_says_where_a_request_stopped(status, body, expected):
    assert probe.reach(status, body) == expected


def test_paths_reports_both_user_agents_and_executes_nothing(mock_url, env, capsys):
    assert probe.main(["paths", "--base-url", mock_url, "--delay", "0"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert set(out["default_ua"]) == {label for label, _ in probe.PATHS} == set(out["browser_ua"])
    assert out["default_ua"]["b2c v1"] == "NOT FOUND"  # the mock implements v3 only


def test_verdict_refuses_to_interpret_a_firewalled_run():
    blocked = {"stk push (control)": "EDGE BLOCK (403, HTML page)", "b2c v3": "EDGE BLOCK (403, HTML page)", "b2c v1": "NOT FOUND"}
    assert probe.verdict(blocked).startswith("BLOCKED")
    usable = {"stk push (control)": "REACHABLE (400)", "b2c v3": "PRODUCT NOT GRANTED", "b2c v1": "NOT FOUND"}
    assert probe.verdict(usable).startswith("usable") and "stk push (control)=REACHABLE (400)" in probe.verdict(usable)


def test_paths_names_the_key_by_its_last_four_characters_only(mock_url, env, capsys):
    probe.main(["paths", "--base-url", mock_url, "--delay", "0"])
    c = capsys.readouterr()
    out = json.loads(c.out)
    assert out["key_ends_with"] == "kkkk" and out["key_length"] == 48 and ("k" * 5) not in c.out and ("s" * 64) not in c.out + c.err


def test_c2b_uses_the_b2c_shortcode_secret_when_no_c2b_one_is_set(mock_url, env, monkeypatch, capsys):
    monkeypatch.delenv("DARAJA_C2B_SHORTCODE", raising=False)
    monkeypatch.setenv("DARAJA_B2C_SHORTCODE", "600555")
    sent = []
    monkeypatch.setattr(probe, "_post", lambda url, token, payload: (sent.append((url.rsplit("/", 1)[-1], payload.get("ShortCode"))) or (200, '{"ResponseCode":"0"}')))
    assert probe.main(["c2b", "--base-url", mock_url]) == 0
    assert sent == [("registerurl", "600555"), ("simulate", "600555")]
    assert "600555" in json.loads(capsys.readouterr().out)["shortcodes_tried"]


def test_c2b_shortcode_precedence(monkeypatch):
    monkeypatch.setenv("DARAJA_B2C_SHORTCODE", "111111")
    monkeypatch.setenv("DARAJA_C2B_SHORTCODE", "222222")
    assert probe.c2b_shortcodes() == ["222222"]
    monkeypatch.delenv("DARAJA_C2B_SHORTCODE")
    assert probe.c2b_shortcodes() == ["111111"]
    monkeypatch.delenv("DARAJA_B2C_SHORTCODE")
    assert probe.c2b_shortcodes() == probe.C2B_CANDIDATES

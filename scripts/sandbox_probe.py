"""Answers the open Daraja questions that need the live sandbox, and reads what Safaricom delivered to a webhook.site receiver.

    python scripts/sandbox_probe.py b2c [--base-url URL]       # does B2C v3 AND v1 exist in the sandbox, and what does each answer?
    python scripts/sandbox_probe.py c2b [--base-url URL]       # C2B v2 register + simulate: the flow that yields a successful callback (is MSISDN masked?)
    python scripts/sandbox_probe.py callbacks UUID             # what arrived at https://webhook.site/UUID; is PhoneNumber masked?

Secrets come from the environment only and are never printed. The B2C probe needs the sandbox "M-Pesa Sandbox" product; without the initiator
variables it says so and exits 0. Exit codes: 0 report produced, 1 a probe could not run at all (network, OAuth), 2 bad usage.

    DARAJA_CONSUMER_KEY, DARAJA_CONSUMER_SECRET             required
    DARAJA_INITIATOR_NAME, DARAJA_SECURITY_CREDENTIAL        from the portal's Test Credentials page (the credential is already encrypted there)
    DARAJA_B2C_SHORTCODE                                     the B2C test shortcode shown on that page
    DARAJA_CALLBACK_URL                                      public https URL for the result and timeout callbacks
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
import uuid

TEST_PHONE = "254708374149"


def _post(url: str, token: str, payload: dict) -> tuple[int, str]:
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), method="POST", headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")


def classify(status: int, body: str) -> str:
    try:
        j = json.loads(body)
    except ValueError:
        j = {}
    if status == 404:
        return "ENDPOINT NOT FOUND"
    if status == 200 and str(j.get("ResponseCode", "")) == "0":
        return "ACCEPTED"
    msg = j.get("errorMessage") or j.get("ResponseDescription") or body[:120]
    return f"REJECTED ({status}: {str(msg)[:100]})"


def b2c(argv: list[str]) -> int:
    base = None
    if "--base-url" in argv:
        base = argv[argv.index("--base-url") + 1].rstrip("/")
    key, secret = os.environ.get("DARAJA_CONSUMER_KEY", ""), os.environ.get("DARAJA_CONSUMER_SECRET", "")
    if not key or not secret:
        print("Refusing to run: DARAJA_CONSUMER_KEY / DARAJA_CONSUMER_SECRET are not set.", file=sys.stderr)
        return 2
    base = base or "https://sandbox.safaricom.co.ke"
    # The portal's Test Credentials page may not show an initiator or shortcode field. Safaricom's documented sandbox initiator is "testapi", and
    # the question asked here (does the v3 / v1 ENDPOINT exist?) is answered the same whatever the shortcode, so both have defaults and are reported.
    initiator, cred = os.environ.get("DARAJA_INITIATOR_NAME") or "testapi", os.environ.get("DARAJA_SECURITY_CREDENTIAL", "")
    shortcode = os.environ.get("DARAJA_B2C_SHORTCODE") or "600000"
    if not cred:
        print(json.dumps({"probe": "b2c", "result": "SKIPPED", "reason": "DARAJA_SECURITY_CREDENTIAL not set; add the 'M-Pesa Sandbox' product to a Daraja app and copy the generated credential from its Test Credentials page"}))
        return 0
    from mpesa.auth import Auth
    from mpesa.exceptions import MpesaError

    try:
        token = Auth(key, secret, sandbox=True, base_url=None if base == "https://sandbox.safaricom.co.ke" else base).token()
    except MpesaError as exc:
        print(json.dumps({"probe": "b2c", "result": "FAILED", "step": "oauth", "error": type(exc).__name__}))
        return 1
    cb = os.environ.get("DARAJA_CALLBACK_URL", "https://example.com/mpesa/b2c")
    common = {"InitiatorName": initiator, "SecurityCredential": cred, "CommandID": "BusinessPayment", "Amount": 10, "PartyA": shortcode, "PartyB": TEST_PHONE, "Remarks": "probe", "QueueTimeOutURL": cb, "ResultURL": cb}
    out = {}
    for version, extra in (("v3", {"OriginatorConversationID": str(uuid.uuid4()), "Occassion": "probe"}), ("v1", {"Occassion": "probe"})):
        status, body = _post(f"{base}/mpesa/b2c/{version}/paymentrequest", token, {**common, **extra})
        out[version] = classify(status, body)
    print(json.dumps({"probe": "b2c", "result": "REPORTED", "initiator": initiator, "shortcode": shortcode, **out}))
    return 0


C2B_CANDIDATES = ["600000", "600977", "600998", "600984", "600981"]  # sandbox test shortcodes vary by account; the first that accepts registerurl is used


def c2b_shortcodes() -> list[str]:
    """The configured shortcode first (DARAJA_C2B_SHORTCODE, else DARAJA_B2C_SHORTCODE: a sandbox account's test shortcode often serves both flows),
    then the common sandbox shortcodes, because Safaricom answers 500 for a shortcode it does not recognise for C2B."""
    configured = [os.environ[n].strip() for n in ("DARAJA_C2B_SHORTCODE", "DARAJA_B2C_SHORTCODE") if os.environ.get(n, "").strip()][:1]
    return configured + [c for c in C2B_CANDIDATES if c not in configured]


def c2b(argv: list[str]) -> int:
    """C2B v2 simulation is the one sandbox flow that produces a SUCCESSFUL callback, so it can show whether the MSISDN is masked."""
    base = argv[argv.index("--base-url") + 1].rstrip("/") if "--base-url" in argv else "https://sandbox.safaricom.co.ke"
    key, secret = os.environ.get("DARAJA_CONSUMER_KEY", ""), os.environ.get("DARAJA_CONSUMER_SECRET", "")
    if not key or not secret:
        print("Refusing to run: DARAJA_CONSUMER_KEY / DARAJA_CONSUMER_SECRET are not set.", file=sys.stderr)
        return 2
    from mpesa.auth import Auth
    from mpesa.exceptions import MpesaError

    try:
        token = Auth(key, secret, sandbox=True, base_url=None if base == "https://sandbox.safaricom.co.ke" else base).token()
    except MpesaError as exc:
        print(json.dumps({"probe": "c2b", "result": "FAILED", "step": "oauth", "error": type(exc).__name__}))
        return 1
    cb = os.environ.get("DARAJA_CALLBACK_URL", "https://example.com/mpesa/c2b")
    tried = {}
    for n, sc in enumerate(c2b_shortcodes()):
        status, body = _post_retry(f"{base}/mpesa/c2b/v2/registerurl", token, {"ShortCode": sc, "ResponseType": "Completed", "ConfirmationURL": cb, "ValidationURL": cb}, tries=4 if n == 0 else 1)
        tried[sc] = {"registerurl": classify(status, body)}
        if tried[sc]["registerurl"] != "ACCEPTED":
            continue
        status, body = _post_retry(f"{base}/mpesa/c2b/v2/simulate", token, {"ShortCode": sc, "CommandID": "CustomerPayBillOnline", "Amount": 10, "Msisdn": TEST_PHONE, "BillRefNumber": "probe"})
        tried[sc]["simulate"] = classify(status, body)
        break
    print(json.dumps({"probe": "c2b", "result": "REPORTED", "shortcodes_tried": tried, "next": "read the callbacks probe: msisdn_in_callback is FULL or MASKED"}))
    return 0


def b2c_result(raw: str) -> tuple[str, str] | None:
    """(ResultCode, ResultDesc) of a B2C/Business result callback, else None. 'ACCEPTED' at the API only means the request was taken; this is the outcome."""
    try:
        r = json.loads(raw)["Result"]
        return str(r["ResultCode"]), str(r.get("ResultDesc", ""))[:100]
    except (ValueError, KeyError, TypeError):
        return None


def _post_retry(url: str, token: str, payload: dict, tries: int = 4, pause: float = 6.0) -> tuple[int, str]:
    """_post, retried on Safaricom 5xx ("Service is currently unreachable" is intermittent), with a pause that also keeps the request rate gentle."""
    status, body = _post(url, token, payload)
    for _ in range(tries - 1):
        if status < 500:
            break
        time.sleep(pause)
        status, body = _post(url, token, payload)
    return status, body


def callbacks(argv: list[str]) -> int:
    if not argv:
        print("usage: sandbox_probe.py callbacks UUID", file=sys.stderr)
        return 2
    try:
        with urllib.request.urlopen(urllib.request.Request(f"https://webhook.site/token/{argv[0]}/requests?sorting=newest", headers={"User-Agent": "mpesa-python-probe"}), timeout=30) as r:
            data = json.loads(r.read().decode("utf-8", "replace")).get("data", [])
    except (urllib.error.URLError, ValueError) as exc:
        print(json.dumps({"probe": "callbacks", "result": "FAILED", "error": type(exc).__name__}))
        return 1
    summary = []
    for item in data:
        raw = item.get("content") or ""
        phone = "ABSENT"
        try:
            for it in json.loads(raw)["Body"]["stkCallback"]["CallbackMetadata"]["Item"]:
                if it.get("Name") == "PhoneNumber":
                    phone = "MASKED" if "*" in str(it.get("Value")) else "FULL"
        except (ValueError, KeyError, TypeError):
            pass
        code = ""
        try:
            code = str(json.loads(raw)["Body"]["stkCallback"]["ResultCode"])
        except (ValueError, KeyError, TypeError):
            code = "n/a"
        msisdn = "ABSENT"
        try:
            m = json.loads(raw).get("MSISDN")
            if m is not None:
                msisdn = "MASKED" if "*" in str(m) else "FULL"
        except (ValueError, AttributeError):
            pass
        entry = {"received": item.get("created_at"), "path": item.get("url", "")[-60:], "stk_result_code": code, "phone_in_callback": phone, "msisdn_in_callback": msisdn}
        res = b2c_result(raw)
        if res:
            entry.update({"result_code": res[0], "result_desc": res[1]})  # ACCEPTED at the API only means the request was taken; this is the outcome
        summary.append(entry)
    print(json.dumps({"probe": "callbacks", "count": len(summary), "callbacks": summary[:10]}))
    return 0


PATHS = [("stk push (control)", "/mpesa/stkpush/v1/processrequest"), ("stk query (control)", "/mpesa/stkpushquery/v1/query"),
         ("b2c v1", "/mpesa/b2c/v1/paymentrequest"), ("b2c v2", "/mpesa/b2c/v2/paymentrequest"), ("b2c v3", "/mpesa/b2c/v3/paymentrequest"),
         ("c2b v1 registerurl", "/mpesa/c2b/v1/registerurl"), ("c2b v2 registerurl", "/mpesa/c2b/v2/registerurl"),
         ("c2b v1 simulate", "/mpesa/c2b/v1/simulate"), ("c2b v2 simulate", "/mpesa/c2b/v2/simulate"),
         ("transaction status", "/mpesa/transactionstatus/v1/query"), ("account balance", "/mpesa/accountbalance/v1/query"),
         ("reversal", "/mpesa/reversal/v1/request"), ("b2b", "/mpesa/b2b/v1/paymentrequest")]
BROWSER_UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"


def reach(status: int, body: str) -> str:
    """Where a request stopped: NOT FOUND, PRODUCT NOT GRANTED, EDGE BLOCK (an HTML page from a firewall, not Daraja), UNAUTHORIZED, or REACHABLE (Daraja's own validation answered)."""
    if status == 404:
        return "NOT FOUND"
    if status == 401 and "apiproduct" in body.lower():
        return "PRODUCT NOT GRANTED"
    if status in (401, 403) and body.lstrip().lower().startswith(("<html", "<!doctype")):
        return f"EDGE BLOCK ({status}, HTML page)"
    if status == 401:
        return "UNAUTHORIZED (no product detail)"
    if status == 403:
        return "FORBIDDEN"
    return f"REACHABLE ({status})"


def verdict(results: dict) -> str:
    """BLOCKED when most answers are edge blocks (the run measured the firewall, not the products); otherwise what the controls say."""
    blocked = sum(1 for v in results.values() if v.startswith("EDGE BLOCK"))
    if blocked * 2 > len(results):
        return f"BLOCKED: {blocked} of {len(results)} answers were firewall pages, so this run says nothing about products; retry later or from another network"
    return "usable: " + ", ".join(f"{k}={v}" for k, v in results.items() if "control" in k)


def _post_ua(url: str, token: str, payload: dict, ua: str | None) -> tuple[int, str]:
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    if ua:
        headers["User-Agent"] = ua
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), method="POST", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")


def paths(argv: list[str]) -> int:
    """Send an EMPTY body to each endpoint (nothing is executed) and report where it stopped, with the default and a browser User-Agent."""
    base = argv[argv.index("--base-url") + 1].rstrip("/") if "--base-url" in argv else "https://sandbox.safaricom.co.ke"
    key, secret = os.environ.get("DARAJA_CONSUMER_KEY", ""), os.environ.get("DARAJA_CONSUMER_SECRET", "")
    if not key or not secret:
        print("Refusing to run: DARAJA_CONSUMER_KEY / DARAJA_CONSUMER_SECRET are not set.", file=sys.stderr)
        return 2
    from mpesa.auth import Auth
    from mpesa.exceptions import MpesaError

    try:
        token = Auth(key, secret, sandbox=True, base_url=None if base == "https://sandbox.safaricom.co.ke" else base).token()
    except MpesaError as exc:
        print(json.dumps({"probe": "paths", "result": "FAILED", "step": "oauth", "error": type(exc).__name__}))
        return 1
    # Safaricom's firewall answers a burst from one IP with an HTML 403 for EVERY endpoint, including the ones that work (seen 2026-10-07), so pace the
    # requests and say so if the very first one is already blocked: a result gathered under a block says nothing about products.
    delay = float(argv[argv.index("--delay") + 1]) if "--delay" in argv else 4.0
    # The last four characters identify WHICH app's key is in the secret (compare with the app card in the portal); too few to help anyone guess the key.
    out: dict = {"probe": "paths", "result": "REPORTED", "key_ends_with": key[-4:], "key_length": len(key), "delay_seconds": delay, "default_ua": {}, "browser_ua": {}}
    for key, ua in (("default_ua", None), ("browser_ua", BROWSER_UA)):
        for label, path in PATHS:
            out[key][label] = reach(*_post_ua(base + path, token, {}, ua))
            time.sleep(delay)
    out["verdict"] = verdict(out["default_ua"])
    print(json.dumps(out))
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not argv or argv[0] not in ("b2c", "c2b", "callbacks", "paths"):
        print(__doc__, file=sys.stderr)
        return 2
    return {"b2c": b2c, "c2b": c2b, "callbacks": callbacks, "paths": paths}[argv[0]](argv[1:])


if __name__ == "__main__":
    sys.exit(main())

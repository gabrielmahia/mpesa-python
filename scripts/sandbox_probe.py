"""Answers the open Daraja questions that need the live sandbox, and reads what Safaricom delivered to a webhook.site receiver.

    python scripts/sandbox_probe.py b2c [--base-url URL]       # does B2C v3 AND v1 exist in the sandbox, and what does each answer?
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
        summary.append({"received": item.get("created_at"), "path": item.get("url", "")[-60:], "stk_result_code": code, "phone_in_callback": phone})
    print(json.dumps({"probe": "callbacks", "count": len(summary), "callbacks": summary[:10]}))
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not argv or argv[0] not in ("b2c", "callbacks"):
        print(__doc__, file=sys.stderr)
        return 2
    return (b2c if argv[0] == "b2c" else callbacks)(argv[1:])


if __name__ == "__main__":
    sys.exit(main())

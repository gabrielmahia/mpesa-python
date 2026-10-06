"""Live Daraja SANDBOX canary: OAuth -> STK Push -> STK Query, with a one-line JSON summary.

Run it to learn whether the sandbox still behaves the way this SDK expects (Safaricom changes the API without notice).
Reads DARAJA_CONSUMER_KEY and DARAJA_CONSUMER_SECRET from the environment, never from arguments, and never prints them. Always sandbox, KES 1,
Safaricom's published test phone.

    python scripts/sandbox_canary.py                              # needs the two variables
    python scripts/sandbox_canary.py --skip-if-no-credentials     # exits 0 with a notice when they are absent (forks, CI without secrets)
    python scripts/sandbox_canary.py --base-url http://localhost:8765   # against daraja-mock, no account needed

Exit codes: 0 healthy (or skipped), 1 a step failed, 2 credentials missing.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

# Safaricom's published sandbox test values (not secrets). The passkey is the same constant as in sandbox_buy_goods_check.py.
SANDBOX_SHORTCODE = "174379"
SANDBOX_PASSKEY = "bfb279f9aa9bdbcf158e97dd71a467cd2e0c893059b10f78e6b72ada1ed2c919"
TEST_PHONE = "254708374149"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Live Daraja sandbox canary")
    ap.add_argument("--skip-if-no-credentials", action="store_true")
    ap.add_argument("--base-url", default=None, help="point at a local test double such as daraja-mock")
    ap.add_argument("--callback-url", default=os.environ.get("DARAJA_CALLBACK_URL", "https://example.com/mpesa/callback"))
    ap.add_argument("--wait", type=float, default=5.0, help="seconds to wait before the status query")
    args = ap.parse_args(argv)

    key = os.environ.get("DARAJA_CONSUMER_KEY", "")
    secret = os.environ.get("DARAJA_CONSUMER_SECRET", "")
    if not key or not secret:
        note = "DARAJA_CONSUMER_KEY / DARAJA_CONSUMER_SECRET are not set"
        if args.skip_if_no_credentials:
            print(json.dumps({"canary": "skipped", "reason": note}))
            return 0
        print(f"Refusing to run: {note}. Create a free sandbox app first: see docs/SANDBOX_SETUP.md", file=sys.stderr)
        return 2

    from mpesa import MpesaClient
    from mpesa.exceptions import AuthenticationError, MpesaError

    client = MpesaClient(key, secret, SANDBOX_SHORTCODE, passkey=os.environ.get("DARAJA_PASSKEY", SANDBOX_PASSKEY), sandbox=True, base_url=args.base_url)
    steps: dict[str, str] = {}
    try:
        push = client.stk_push(TEST_PHONE, 1, "CANARY", "Canary", callback_url=args.callback_url)
        steps["oauth"] = "ok"
        steps["stk_push"] = "ok"
        time.sleep(args.wait)
        query = client.stk_query(push.checkout_request_id)
        steps["stk_query"] = f"ok (result_code {query.result_code})"
    except AuthenticationError as exc:
        steps["oauth"] = f"FAILED: {type(exc).__name__}"
    except (MpesaError, ValueError) as exc:
        steps["oauth"] = steps.get("oauth", "ok")
        steps["stk_query" if "stk_push" in steps else "stk_push"] = f"FAILED: {type(exc).__name__}: {str(exc)[:120]}"
    healthy = steps.get("oauth") == "ok" and steps.get("stk_push") == "ok" and steps.get("stk_query", "").startswith("ok")
    print(json.dumps({"canary": "healthy" if healthy else "BROKEN", **steps}))
    return 0 if healthy else 1


if __name__ == "__main__":
    sys.exit(main())

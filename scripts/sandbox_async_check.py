"""Live Daraja SANDBOX check of the NATIVE ASYNC client: concurrent OAuth, STK Push, STK Query. One JSON summary line; no secret is printed.

    DARAJA_CONSUMER_KEY=... DARAJA_CONSUMER_SECRET=... python scripts/sandbox_async_check.py

Uses Safaricom's published sandbox shortcode, passkey and test phone, KES 1. The sandbox cannot complete an STK payment, so this proves the client's transport,
OAuth caching under concurrency and request/response handling, not that a payment succeeds. Exit codes: 0 healthy, 1 a step failed, 2 credentials missing.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys

SANDBOX_SHORTCODE = "174379"
SANDBOX_PASSKEY = "bfb279f9aa9bdbcf158e97dd71a467cd2e0c893059b10f78e6b72ada1ed2c919"  # published by Safaricom, not a secret
TEST_PHONE = "254708374149"


async def run() -> dict:
    from mpesa.async_client import MpesaAsyncClient
    from mpesa.exceptions import MpesaError

    out: dict = {"check": "async-sandbox", "steps": {}}
    cb = os.environ.get("DARAJA_CALLBACK_URL", "https://example.com/payments/callback").rstrip("/") + "/payments/stk"
    async with MpesaAsyncClient(os.environ["DARAJA_CONSUMER_KEY"], os.environ["DARAJA_CONSUMER_SECRET"], SANDBOX_SHORTCODE, SANDBOX_PASSKEY, sandbox=True) as client:
        try:
            tokens = await asyncio.gather(*[client._token() for _ in range(5)])
            out["steps"]["oauth_concurrent"] = {"ok": len(set(tokens)) == 1, "calls": 5, "distinct_tokens": len(set(tokens))}
        except MpesaError as exc:
            out["steps"]["oauth_concurrent"] = {"ok": False, "error": type(exc).__name__}
            return out
        try:
            r = await client.stk_push(TEST_PHONE, 1, "asyncCheck", "async check", callback_url=cb)
            out["steps"]["stk_push"] = {"ok": bool(r.checkout_request_id), "response_code": getattr(r, "response_code", None), "has_checkout_id": bool(r.checkout_request_id)}
            cid = r.checkout_request_id
        except MpesaError as exc:
            out["steps"]["stk_push"] = {"ok": False, "error": type(exc).__name__, "message": str(exc)[:120]}
            return out
        await asyncio.sleep(6)
        for attempt in range(1, 5):  # the sandbox query is intermittently HTTP 500
            try:
                q = await client.stk_query(cid)
                out["steps"]["stk_query"] = {"ok": True, "attempt": attempt, "result_code": q.result_code}
                break
            except MpesaError as exc:
                out["steps"]["stk_query"] = {"ok": False, "attempt": attempt, "error": type(exc).__name__, "message": str(exc)[:100]}
                await asyncio.sleep(8)
    return out


def main() -> int:
    if not os.environ.get("DARAJA_CONSUMER_KEY") or not os.environ.get("DARAJA_CONSUMER_SECRET"):
        print("Refusing to run: DARAJA_CONSUMER_KEY / DARAJA_CONSUMER_SECRET are not set.", file=sys.stderr)
        return 2
    result = asyncio.run(run())
    healthy = all(s.get("ok") for s in result["steps"].values()) and {"oauth_concurrent", "stk_push"} <= set(result["steps"])
    result["healthy"] = healthy
    print(json.dumps(result))
    return 0 if healthy else 1


if __name__ == "__main__":
    sys.exit(main())

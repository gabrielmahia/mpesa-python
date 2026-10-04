"""Sandbox-only check: does Daraja's SANDBOX accept an STK Push with a PartyB different from the shortcode?

Reads credentials from the environment (never from arguments, never printed) and refuses to run without them. It always uses the
sandbox host. It sends KES 1 requests to Safaricom's published test phone number.

    export DARAJA_CONSUMER_KEY=...        # from your Daraja portal app (My Apps)
    export DARAJA_CONSUMER_SECRET=...
    export DARAJA_CALLBACK_URL=https://...   # a public HTTPS URL you can watch (e.g. a webhook.site address)
    export DARAJA_TILL=...                   # optional: the PartyB to test (defaults to the shortcode)
    python scripts/sandbox_buy_goods_check.py

What it can show: the sandbox accepted (or rejected) each request, with the sandbox's own response codes, and what the status query
reports. What it cannot show: that PRODUCTION accepts a distinct till. The sandbox may not distinguish PartyB values at all.
"""
import os
import sys
import time

# Published Safaricom sandbox test values (not secrets): shortcode, LNM passkey, and the documented test phone.
SANDBOX_SHORTCODE = "174379"
SANDBOX_PASSKEY = "bfb279f9aa9bdbcf158e97dd71a467cd2e0c893059b10f78e6b72ada1ed2c919"
TEST_PHONE = "254708374149"
REQUIRED = ("DARAJA_CONSUMER_KEY", "DARAJA_CONSUMER_SECRET", "DARAJA_CALLBACK_URL")


def main() -> int:
    missing = [k for k in REQUIRED if not os.environ.get(k)]
    if missing:
        print("Refusing to run: missing environment variables: " + ", ".join(missing), file=sys.stderr)
        return 2
    if not os.environ["DARAJA_CALLBACK_URL"].startswith("https://"):
        print("Refusing to run: DARAJA_CALLBACK_URL must be an https:// URL.", file=sys.stderr)
        return 2

    from mpesa import MpesaClient

    shortcode = os.environ.get("DARAJA_SHORTCODE", SANDBOX_SHORTCODE)
    client = MpesaClient(
        consumer_key=os.environ["DARAJA_CONSUMER_KEY"],
        consumer_secret=os.environ["DARAJA_CONSUMER_SECRET"],
        shortcode=shortcode,
        passkey=os.environ.get("DARAJA_PASSKEY", SANDBOX_PASSKEY),
        sandbox=True,  # fixed: this script never talks to production
    )
    till = os.environ.get("DARAJA_TILL") or shortcode
    cases = [
        ("A control: paybill, PartyB = shortcode", {"transaction_type": "CustomerPayBillOnline"}),
        (f"B buy goods, PartyB = {'a distinct till' if till != shortcode else 'shortcode (no DARAJA_TILL set)'}",
         {"transaction_type": "CustomerBuyGoodsOnline", "party_b": till}),
    ]
    sent = []
    for label, kwargs in cases:
        print(f"\n== {label}")
        try:
            r = client.stk_push(TEST_PHONE, 1, "SBXCHECK", "Sandbox check", callback_url=os.environ["DARAJA_CALLBACK_URL"], **kwargs)
            print("  accepted by the sandbox:", r.response_description, "|", r.customer_message)
            print("  CheckoutRequestID:", r.checkout_request_id)
            sent.append((label, r.checkout_request_id))
        except Exception as exc:  # report the sandbox's own error, never credentials
            print(f"  REJECTED: {type(exc).__name__}: {getattr(exc, 'message', exc)}")
    if sent:
        time.sleep(20)
        print("\n== status queries (after 20 s)")
        for label, cid in sent:
            try:
                q = client.stk_query(cid)
                print(f"  {label}: result_code={q.result_code!r} is_paid={q.is_paid}")
            except Exception as exc:
                print(f"  {label}: query failed: {type(exc).__name__}: {getattr(exc, 'message', exc)}")
    print("\nNow look at your callback URL for what Safaricom actually delivered, and record both outcomes. See docs/SANDBOX_BUY_GOODS_CHECK.md.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

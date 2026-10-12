# Native asyncio client (optional extra)

Install the opt-in, nonblocking HTTP transport:

```bash
pip install "daraja-v3[async]"
```

The default `MpesaClient` remains synchronous and dependency-free. With the optional extra, `MpesaAsyncClient` performs OAuth and Daraja HTTP calls using `aiohttp` rather than occupying a FastAPI event-loop thread. Use the async context manager to close connections:

```python
from mpesa import MpesaAsyncClient

async def request_payment():
    async with MpesaAsyncClient(
        consumer_key="your_key",
        consumer_secret="your_secret",
        shortcode="174379",
        passkey="your_lnm_passkey",
        sandbox=True,
    ) as client:
        result = await client.stk_push(
            phone="0112345678",
            amount=500,
            reference="Order-001",
            callback_url="https://yourapp.example/payments/stk/callback",
        )
        # Initiated is NOT the same as paid; store this ID for reconciliation.
        return result.checkout_request_id
```

In FastAPI, prefer a long-lived client created at startup and closed at shutdown. Each client holds a per-instance, lock-protected OAuth cache and an HTTP session. The async methods correspond to `stk_push`, `stk_query`, `b2c`, `c2b_register_urls`, and `account_balance`. Webhook parsing stays a synchronous pure function: `MpesaAsyncClient.parse_stk_callback(body)`.

## Callback URL and delivery lessons

- Use a public HTTPS callback endpoint that your application actually serves, e.g. `/payments/stk/callback`. A production integrator reported Safaricom rejecting a URL containing the substring `mpesa`; other implementers have reported similar filtering. This is **field feedback**, not a verified universal Safaricom rule. Changing paths is a pragmatic compatibility measure; check your own Daraja environment, DNS, TLS, and reverse-proxy configuration.
- For asynchronous transaction notifications, validate structure, authenticate/validate source where practicable, persist the incoming event to a **durable** queue/inbox, then respond promptly with 2xx. Do not do expensive order processing during the callback request. Returning 2xx before persistence risks payment loss if the worker crashes; in-process `BackgroundTasks` alone is not a durable queue.
- Deduplicate atomically with a database uniqueness constraint / transactional upsert keyed on `CheckoutRequestID` (and preferably event type); retries and parallel deliveries must not mark an order paid twice. Also reconcile the `MpesaReceiptNumber` and the original request's amount/order. For events missing identifiers, quarantine for review; do not silently grant value.
- Treat callbacks as untrusted input, not sufficient payment proof for high-value fulfilment. Reconcile via authenticated Daraja STK Query and stored initiation data where appropriate; design a pending/retry state and alert on stuck payments.
- `stk_push()` returns **initiation**, not settlement. `stk_query()` and callbacks are separate operations.
- Phone numbers in callbacks may be masked: join by `CheckoutRequestID`, not `PhoneNumber`.

See [the SDK README](../README.md) and [mpesa-webhooks](https://github.com/gabrielmahia/mpesa-webhooks) for a related callback-handler project. Review that handler's storage/ack/verification semantics for your deployment; an in-memory idempotency store or background handler is not sufficient for multi-worker production systems.

## Error handling

As with the sync client, catch `ValidationError` for local input errors, `AuthenticationError` for OAuth errors, `MpesaTimeoutError` for timeouts, and `MpesaError` for HTTP/other client failures. A timed-out POST might still have reached Safaricom: reconcile before submitting a duplicate payment request.

```python
from mpesa import MpesaAsyncClient, MpesaTimeoutError

async with MpesaAsyncClient("key", "secret", "174379", passkey="passkey") as client:
    try:
        pending = await client.stk_push("0712345678", 100, "Order-002",
            callback_url="https://yourapp.example/payments/stk/callback")
    except MpesaTimeoutError:
        # Unknown initiation status. Flag for reconciliation; do not blindly retry.
        ...
```

Do not place real Daraja credentials in source code or GitHub issues; examples above use placeholders.

# mpesa-python

**Production Python SDK for Safaricom M-Pesa Daraja v3.**

[![Tests](https://img.shields.io/badge/tests-33%20passing-brightgreen)](https://github.com/gabrielmahia/mpesa-python/actions)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](https://pypi.org/project/mpesa-python/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![PyPI](https://img.shields.io/badge/pypi-mpesa--python-orange)](https://pypi.org/project/mpesa-python/)

Zero external dependencies. Type-annotated. Stripe-quality error handling.

```python
from mpesa import MpesaClient

client = MpesaClient(
    consumer_key="your_key",
    consumer_secret="your_secret",
    shortcode="174379",
    passkey="your_lnm_passkey",
    sandbox=True,           # flip to False when you go live
)

# Prompt customer phone to enter PIN
result = client.stk_push(
    phone="0712345678",     # any Kenyan format — normalised automatically
    amount=500,
    reference="Order-001",
    callback_url="https://yourapp.com/mpesa/callback",
)
print(result.checkout_request_id)
```

---

## Why this exists

Every Kenya fintech project needs M-Pesa. Most of them roll their own wrapper — usually a 200-line `mpesa_utils.py` with no tests, swallowed exceptions, and phone number bugs. This is the library those teams should be importing instead.

**Design goals (borrowed from Stripe's Python SDK):**
- Fail before the network call when possible — `ValidationError` catches bad inputs locally
- Typed results — no `response["Body"]["stkCallback"]["CallbackMetadata"]["Item"][0]["Value"]`
- Token caching — never burn a request on an expired token
- Composable exceptions — catch `MpesaError` broadly or specific subclasses narrowly
- Zero dependencies — drop into any environment without conflicts

---

## Installation

```bash
pip install mpesa-python
```

Or from source:
```bash
git clone https://github.com/gabrielmahia/mpesa-python
cd mpesa-python
pip install -e ".[dev]"
```

---

## Supported APIs

| API | Method | What it does |
|-----|--------|--------------|
| STK Push | `client.stk_push()` | Prompt customer phone to pay |
| STK Query | `client.stk_query()` | Check STK push status |
| B2C | `client.b2c()` | Send money to customer wallet |
| C2B Register | `client.c2b_register_urls()` | Register payment notification URLs |
| Account Balance | `client.account_balance()` | Query your shortcode balance |
| Webhook parsing | `MpesaClient.parse_stk_callback()` | Parse Safaricom's webhook body |

Roadmap: Reversal, Transaction Status, QR Code, Ratiba (recurring payments)

---

## Usage guide

### STK Push + webhook

```python
# 1. Initiate push
result = client.stk_push(
    phone="0712345678",
    amount=1500,
    reference="Invoice-2024-042",
    description="Subscription",
    callback_url="https://yourapp.com/mpesa/stk/callback",
)

# 2. Store result.checkout_request_id against your order

# 3. In your webhook handler:
from mpesa import MpesaClient

def handle_stk_callback(request_body: dict):
    payment = MpesaClient.parse_stk_callback(request_body)
    if payment["paid"]:
        receipt = payment["mpesa_receipt"]   # e.g. "NLJ7RT61SV"
        amount  = payment["amount"]          # e.g. 1500
        phone   = payment["phone"]           # e.g. "254712345678"
        # update your order, send confirmation email, etc.
```

### B2C disbursement

```python
result = client.b2c(
    phone="0712345678",
    amount=5000,
    remarks="Monthly stipend",
    initiator_name="testapi",             # from your Daraja portal
    security_credential="encrypted_cred",
    callback_url="https://yourapp.com/mpesa/b2c/result",
    queue_timeout_url="https://yourapp.com/mpesa/b2c/timeout",
)
print(result.conversation_id)  # use to reconcile
```

### Error handling

```python
from mpesa import MpesaClient
from mpesa.exceptions import ValidationError, AuthenticationError, TransactionError, MpesaError

try:
    result = client.stk_push(phone="bad-phone", amount=100, reference="ref")
except ValidationError as e:
    # Bad input — no network call was made
    print(f"Fix your input: {e.message} (code: {e.code})")
except AuthenticationError as e:
    # Check your CONSUMER_KEY and CONSUMER_SECRET
    print(f"Auth failed: {e.message}")
except TransactionError as e:
    # M-Pesa returned a non-zero result (user cancelled, insufficient funds, etc.)
    print(f"Transaction failed: {e.message} (M-Pesa code: {e.code})")
    print(f"Raw response: {e.raw}")
except MpesaError as e:
    # Catch-all for any other SDK error
    print(f"Error: {e.message}")
```

### Phone number normalisation

The SDK accepts any Kenyan phone format and normalises to `2547XXXXXXXX`:

```python
from mpesa.validators import phone

phone("0712345678")      # → "254712345678"
phone("+254712345678")   # → "254712345678"
phone("254712345678")    # → "254712345678"
phone("712345678")       # → "254712345678"
phone("bad-number")      # → raises ValidationError
```

---

## Development

```bash
# Clone and install dev dependencies
git clone https://github.com/gabrielmahia/mpesa-python
cd mpesa-python
pip install -e ".[dev]"

# Run tests
pytest

# Lint
ruff check .

# Type check
mypy mpesa/
```

### Running integration tests

Integration tests require Daraja sandbox credentials. Set environment variables:

```bash
export MPESA_CONSUMER_KEY="your_sandbox_key"
export MPESA_CONSUMER_SECRET="your_sandbox_secret"
export MPESA_SHORTCODE="174379"
export MPESA_PASSKEY="your_sandbox_passkey"
export MPESA_CALLBACK_URL="https://your-ngrok-tunnel.ngrok.io/mpesa/callback"

pytest tests/integration/ -v
```

Get sandbox credentials free at [developer.safaricom.co.ke](https://developer.safaricom.co.ke).

---

## Contributing

Issues and PRs welcome. See [CONTRIBUTING.md](CONTRIBUTING.md).

This SDK follows the project conventions in [nairobi-stack](https://github.com/gabrielmahia/nairobi-stack) — the engineering guide for building products in East Africa.

---

## License

MIT — use freely in commercial and open source projects. Attribution appreciated.

---

*Built by a Kenyan engineer who has written this wrapper from scratch one too many times.*

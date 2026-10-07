# Daraja sandbox: setup, keeping it working, and testing without it

This guide records what was **verified on 2026-10-05/06** against a brand-new Safaricom developer account. Anything not verified is marked **UNVERIFIED**.

## What you need
- A free Safaricom developer account (https://developer.safaricom.co.ke), Python 3, about ten minutes.
- No keys are shared in this repository, and none can be: a Daraja Consumer Key and Secret belong to one developer account. Every person who clones or forks creates their own free sandbox app (below).

## 1. Create the sandbox app
1. Log in, open **My Apps**, click **Create Sandbox App**.
2. **Application Name:** letters, numbers, spaces and underscores only (**no hyphens**). For example `mpesa_sandbox`.
3. **Products:** tick only **Lipa Na M-Pesa Sandbox** ("For Lipa Na M-Pesa express"). That is STK Push and STK Query, which is all the checks below need. Leave the other products off until you need them.
4. Click **Create App**. The app card shows **Consumer Key** and **Consumer Secret** (masked: use the copy icons; selecting the text copies only the masked form), and **Passkey** and **Short Code** show `N/A`. That is expected.
5. Use Safaricom's published sandbox test values for the shortcode and passkey: shortcode `174379`, and the test passkey held as `SANDBOX_PASSKEY` in `scripts/sandbox_canary.py`. They worked on a new account on 2026-10-06.

The portal's **Test Credentials** page is a *Security Credential generator* (it encrypts an initiator password). You do not need it for STK Push. It matters only for B2C, status, balance and reversal, which also need the "M-Pesa Sandbox" product and an initiator.

## 2. A callback URL
Safaricom posts the STK result to a public HTTPS URL. For testing, open https://webhook.site and use the unique URL it shows you. No server is needed.

## 3. Run the check
- **Windows (PowerShell, no admin needed):** `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\setup_sandbox.ps1`
- **macOS / Linux:** `bash scripts/setup_sandbox.sh`

Both create a private environment under `~/mpesa-sandbox`, install `pesa-cli`, ask for the key and secret (kept in that window only, never written to disk), then run OAuth, a KES 1 STK Push to Safaricom's public test phone `254708374149`, and a status query. The Windows script was run end to end on 2026-10-06; the macOS/Linux script has been syntax-checked and linted but not run against Safaricom (**UNVERIFIED**).

**What good looks like (verified):** `Authenticated`; a `Checkout ID` starting `ws_CO_`; a callback arriving at your webhook.site URL with `ResultCode 1037` and "No response from user" (the test phone never answers, so this is the expected outcome); the status query reporting the same `1037`.

## 4. Variable names differ by project
| Project | Key | Secret | Shortcode / passkey | Callback | Sandbox switch |
|---|---|---|---|---|---|
| `pesa-cli`, `scripts/` here | `DARAJA_CONSUMER_KEY` | `DARAJA_CONSUMER_SECRET` | `DARAJA_SHORTCODE`, `DARAJA_PASSKEY` | `DARAJA_CALLBACK_URL` | `DARAJA_ENVIRONMENT` |
| `mpesa-mcp` | `MPESA_CONSUMER_KEY` | `MPESA_CONSUMER_SECRET` | `MPESA_SHORTCODE`, `MPESA_PASSKEY` | `MPESA_CALLBACK_URL` (required) | `MPESA_SANDBOX` (default true) |
| `jumuia` | `MPESA_CONSUMER_KEY` | `MPESA_CONSUMER_SECRET` | `MPESA_SHORTCODE`, `MPESA_PASSKEY` | `MPESA_CALLBACK_URL` | `MPESA_ENV` |

## 5. Where to keep your keys
- In a password manager, in an entry of its own. Never in the repository, in chat, or in a `.env` that is committed.
- For the weekly canary (below) as GitHub Actions secrets in **your** copy: *Settings, Secrets and variables, Actions, New repository secret*, named `DARAJA_CONSUMER_KEY` and `DARAJA_CONSUMER_SECRET`. GitHub does not pass secrets to forks, so on a fork the canary skips cleanly.

## 6. The canary: know when Safaricom changes something
`scripts/sandbox_canary.py` runs OAuth, STK Push and STK Query against the live sandbox and prints one JSON line (`healthy` or `BROKEN`). `.github/workflows/sandbox-canary.yml` runs it weekly and skips when no secrets exist. It is a way to find out about API changes before users do.

## 7. Testing without any account
`MpesaClient` accepts an optional `base_url`, for pointing at a local test double such as [daraja-mock](https://pypi.org/project/daraja-mock/):

```python
from daraja_mock import DarajaMock
from mpesa import MpesaClient

mock = DarajaMock()
url = mock.run_thread(port=18080)
client = MpesaClient("any", "any", "174379", passkey="any", base_url=url)
result = client.stk_push("0712345678", 10, "REF", "Test", callback_url="https://example.com/cb")
```

`base_url` must be `https://`, or `http://` for `localhost` only, because the client sends your consumer secret to whatever host it is given; anything else raises `ValueError`.

## If something fails
- **`pesa auth` reports 400 or 401:** the key or secret was copied masked or truncated. Re-copy with the copy icons.
- **STK Push is rejected:** re-check that the shortcode is `174379` and the passkey is the published test value.
- **No callback arrives:** the callback URL must be public HTTPS. Without `DARAJA_CALLBACK_URL`, `pesa-cli` silently falls back to `https://example.com/mpesa/callback`.

## What the sandbox actually did (checked 2026-10-06 and 2026-10-07 with the "Sandbox probe" and "Sandbox paths" workflows)
- **C2B v2 masks the customer's phone number.** With a registered URL, a simulated payment's confirmation callback carried `"MSISDN": "2547 ***** 149"` (first four digits, five asterisks, last three). Match C2B payments on `TransID` or `BillRefNumber`, never on the phone. (Checked 2026-10-07 with shortcode `600000`.)
- **B2C `v3` and `v1` both exist and accept requests** (HTTP 200 "accepted"). That is not success: the result callback said `ResultCode 2001 "The initiator information is invalid"` until the initiator name and security credential match the app. `v2` returns 404.
- **Buy Goods is rejected on the sandbox paybill shortcode** (`400 Invalid TransactionType` for `CustomerBuyGoodsOnline`). The paybill control is accepted. Buy Goods can only be exercised with a real till at go-live.
- **A failed STK payment's callback has no phone field** (`ResultCode` 1032 or 1037).
- **Products must be on the app whose key you use.** An app with only Lipa Na M-Pesa Sandbox gets `401 no apiproduct match found` on B2C and C2B; a new app with both products ticked at creation reached every endpoint (the "Sandbox paths" workflow shows `REACHABLE` for each).
- **Safaricom's firewall blocks a burst from one IP** with an HTML 403 on every endpoint, including working ones, and the sandbox returns intermittent `500 Service is currently unreachable`. Pace requests, retry 5xx, and distrust any run in which the STK controls fail.
- **C2B register answers `HTTP 200 "Success"`** (no `ResponseCode`); a shortcode that is already registered answers `500 Duplicate notification info`; a shortcode the sandbox does not recognise for C2B can answer `500 Service is currently unreachable`.

## Still unknown
- **Whether STK callbacks mask the phone number on a successful payment.** The sandbox test phone cannot complete a payment, so this cannot be observed here. One secondary source says they do, and C2B v2 does (above). `parse_stk_callback` returns the field as a string either way; match by `checkout_request_id` or receipt, not by phone.
- **Whether B2C `v1` still works in production** (it accepts requests in the sandbox). The Safaricom-derived spec says `v3` is current; this SDK uses `v3`.
- **Whether a B2C payment succeeds in the sandbox** once the initiator name and security credential match (not yet seen; needs the initiator name and credential from the app's Test Credentials page).

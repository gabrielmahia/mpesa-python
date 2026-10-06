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

## What the sandbox has actually said (verified 2026-10-06, app with only "Lipa Na M-Pesa Sandbox")
- **OAuth, STK Push and STK Query work.** The status query is **intermittently `500`** even when the push succeeded; retry it (the canary retries three times).
- **Callbacks arrive within about 30 seconds** at a public HTTPS URL. Observed `ResultCode 1037` (no response) and `1032` (cancelled), both in the same session, so do not assume one. A failed payment's callback has **no phone field**.
- **Buy Goods with the standard shortcode `174379`:** `400 Invalid TransactionType`. The sandbox ties the transaction type to the shortcode type, so a real Buy Goods test needs a sandbox till number, which the portal did not give this account.
- **B2C and C2B v2:** `401 ... no apiproduct match found` on this app. They need the **M-Pesa Sandbox** product, which is a different product from Lipa Na M-Pesa Sandbox. Create a second sandbox app with **both** ticked and use its key and secret.
- **The Test Credentials page has no shortcode or initiator field** on this account. The probe defaults them (`testapi`, `600000`) because the question it asks (does the endpoint exist and what does it say?) is answered the same either way.

## Still unknown
- **B2C `v3` or `v1`:** a Safaricom-derived spec says v3 is current. The live answer is blocked on the product above.
- **UNVERIFIED:** whether the STK callback `PhoneNumber` is masked. One secondary source says so; the sandbox cannot show it (no successful payment). C2B v2 *can* produce a successful callback, so after the product is added the probe's `c2b` step reports `msisdn_in_callback: FULL` or `MASKED`. `parse_stk_callback` returns the field as a string either way; match payments by `checkout_request_id` or receipt, not by phone.

# Answering the open Daraja questions without pasting secrets anywhere

Three questions need Safaricom's live sandbox. A workflow in this repository asks it and prints the answers in the job log, so **the keys never go into a chat, a file or a commit**: they live only as GitHub Actions secrets in your repository.

| Question | Can the sandbox answer it? |
|---|---|
| Buy Goods with a distinct PartyB | Yes, with the app you already have (add `DARAJA_TILL` if the portal shows a Buy Goods till) |
| B2C `v3` or `v1` | Yes, but the app needs the **M-Pesa Sandbox** product |
| Is the STK callback `PhoneNumber` masked? | **No.** The sandbox test phone cannot complete a payment, and a failed payment has no phone field. Our code does not depend on it (it matches on the checkout id and receipt number). Only a real production payment can show it |

## One-time setup
1. In *Settings, Secrets and variables, Actions, New repository secret* add `DARAJA_CONSUMER_KEY` and `DARAJA_CONSUMER_SECRET` (the copy icons on your app card).
2. For the B2C question: in the Daraja portal edit or create an app and tick **M-Pesa Sandbox** (as well as Lipa Na M-Pesa Sandbox). On its **Test Credentials** page enter the initiator password and copy: the initiator name (`DARAJA_INITIATOR_NAME`), the generated **Security Credential** (`DARAJA_SECURITY_CREDENTIAL`, already encrypted there) and the B2C shortcode (`DARAJA_B2C_SHORTCODE`).
3. Run it: *Actions, Sandbox probe, Run workflow*.

Anyone with admin rights on a fork can do the same with their own keys; GitHub does not pass secrets to forks, so nothing leaks.

## Reading the result
- `b2c`: `v3`/`v1` each report `ACCEPTED`, `ENDPOINT NOT FOUND` or `REJECTED (...)`. Documentation (an OpenAPI spec generated from the portal, 2026-07-17) says v3 is current and v1/v2 were superseded; this shows what the sandbox actually does.
- `callbacks`: what arrived at the receiver, with `phone_in_callback` set to `FULL`, `MASKED` or `ABSENT`. In the sandbox expect `ABSENT` with `stk_result_code 1037`.

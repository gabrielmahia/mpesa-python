# Answering the open Daraja questions without pasting secrets anywhere

Three questions need Safaricom's live sandbox. A workflow in this repository asks it and prints the answers in the job log, so **the keys never go into a chat, a file or a commit**: they live only as GitHub Actions secrets in your repository.

| Question | Can the sandbox answer it? |
|---|---|
| Buy Goods with a distinct PartyB | **Answered 2026-10-06:** with shortcode `174379` the sandbox returns `400 Invalid TransactionType`. A genuine Buy Goods test needs a sandbox till this account does not have |
| B2C `v3` or `v1` | Yes, once the app has the **M-Pesa Sandbox** product (see below) |
| Is the callback phone masked? | **STK: no.** A failed payment has no phone field. **C2B v2: yes**, once the product is added: its simulation produces a successful callback |

## One-time setup
1. Repository secrets (*Settings, Secrets and variables, Actions*): `DARAJA_CONSUMER_KEY` and `DARAJA_CONSUMER_SECRET` (the copy icons on the app card).
2. **For B2C and C2B:** the app behind those two secrets must have **both** products ticked, *Lipa Na M-Pesa Sandbox* **and** *M-Pesa Sandbox*. An app with only the first gets `401 no apiproduct match found` for both. Create a new sandbox app with both ticked and replace the two secrets with its key and secret.
3. For B2C also add `DARAJA_SECURITY_CREDENTIAL`: on the app's *Test Credentials* page enter the initiator password and copy the generated credential. `DARAJA_INITIATOR_NAME` (default `testapi`) and `DARAJA_B2C_SHORTCODE` (default `600000`) are optional: that page may have no field for them, and the endpoint question is answered either way.
4. Run it: *Actions, Sandbox probe, Run workflow*.

Anyone with admin rights on a fork can do the same with their own keys; GitHub does not pass secrets to forks, so nothing leaks.

## Reading the result
- `b2c`: `v3`/`v1` each report `ACCEPTED`, `ENDPOINT NOT FOUND` or `REJECTED (...)`. Documentation (an OpenAPI spec generated from the portal, 2026-07-17) says v3 is current and v1/v2 were superseded; this shows what the sandbox actually does.
- `c2b`: for each candidate test shortcode, whether `registerurl` and `simulate` were `ACCEPTED`.
- `callbacks`: what arrived at the receiver. `phone_in_callback` (STK) and `msisdn_in_callback` (C2B) are `FULL`, `MASKED` or `ABSENT`. For a failed STK payment expect `ABSENT` with `stk_result_code` 1037 or 1032.

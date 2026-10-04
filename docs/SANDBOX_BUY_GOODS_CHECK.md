# Sandbox check: PartyB with Buy Goods

**Why:** the unit tests show we send the PartyB you give us, but only Safaricom can say whether it accepts a request where PartyB (the till) differs from the shortcode, and whether the callback arrives. The sandbox can answer part of that; production is the only full answer.

## 1. Get sandbox credentials (once)
1. Sign in at https://developer.safaricom.co.ke (your account). Open **My Apps**: https://developer.safaricom.co.ke/MyApps
2. Create an app (or open an existing one) and tick the **M-Pesa Express (Lipa na M-Pesa Online) Sandbox** product.
3. Copy the app's **Consumer Key** and **Consumer Secret**. Keep them out of chats, issues and git. The shortcode `174379`, the test passkey and the test phone `254708374149` are Safaricom's published test values, already built into the script.

## 2. A callback address you can watch
Callbacks must be a public HTTPS URL. Easiest: open https://webhook.site, copy your unique URL, and leave the tab open. (Or run your own receiver behind a tunnel such as ngrok.)

## 3. Run it
```bash
pip install "daraja-v3>=0.1.1"
export DARAJA_CONSUMER_KEY=...        # from step 1
export DARAJA_CONSUMER_SECRET=...
export DARAJA_CALLBACK_URL=https://webhook.site/your-unique-id
export DARAJA_TILL=123456             # optional: any 5-7 digit value to use as PartyB
python scripts/sandbox_buy_goods_check.py
```
It is sandbox-only, sends KES 1 to Safaricom's test number, never prints your credentials, and refuses to run without them.

## 4. Read the result
| What you see | What it means |
|---|---|
| A and B both accepted, callbacks arrive | the sandbox accepts the payload shape. It does NOT prove production accepts a distinct till. |
| A accepted, B rejected | the sandbox distinguishes PartyB; copy the exact error text into the issue, it is the evidence we lack. |
| Both rejected | credentials, product not enabled, or callback URL; fix that first. |
| No callback after a minute | normal in the sandbox at times; use the status query result, not silence, as the evidence. |

## 5. What this cannot settle
Production behaviour with a real till and a different head-office shortcode needs a real till and real money (a small amount). That is a decision for the account owner, not something to automate. Record both outcomes in the repository issue tracker; do not paste secrets.

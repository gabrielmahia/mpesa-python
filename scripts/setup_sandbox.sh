#!/usr/bin/env bash
# Sandbox check for macOS and Linux. Installs only under ~/mpesa-sandbox. Creates a private Python environment, installs pesa-cli, asks for your
# Daraja sandbox Consumer Key and Secret (kept in this shell only, never written to disk), then runs:
#   OAuth -> STK Push of KES 1 to Safaricom's public test phone -> status query.
# Run:  bash scripts/setup_sandbox.sh        Guide: docs/SANDBOX_SETUP.md
set -euo pipefail

BASE="${HOME}/mpesa-sandbox"
VENV="${BASE}/venv"
mkdir -p "${BASE}"

cleanup() { unset DARAJA_CONSUMER_KEY DARAJA_CONSUMER_SECRET DARAJA_PASSKEY DARAJA_SHORTCODE DARAJA_CALLBACK_URL DARAJA_ENVIRONMENT PESA_CONFIG; echo; echo "Credentials cleared from this shell."; }
trap cleanup EXIT
say() { echo; echo "== $1"; }
need_len() { if [[ "$2" == *"*"* || "$2" =~ [[:space:]] || ${#2} -lt 20 ]]; then echo "$1 looks wrong (length ${#2}). Use the portal's copy icon, not selected text, which is masked." >&2; exit 1; fi; echo "$1: ${#2} characters received"; }

say "Step 1 of 6: looking for Python 3"
command -v python3 >/dev/null || { echo "Python 3 was not found. Install it from https://www.python.org/downloads/ and run this script again." >&2; exit 1; }
python3 --version

say "Step 2 of 6: creating a private Python environment in ${VENV}"
python3 -m venv "${VENV}"

say "Step 3 of 6: installing pesa-cli (this can take a minute)"
"${VENV}/bin/python" -m pip install --quiet --upgrade pip pesa-cli
PESA="${VENV}/bin/pesa"
[[ -x "${PESA}" ]] || { echo "pesa was not created at ${PESA}" >&2; exit 1; }
echo "Installed: ${PESA}"

say "Step 4 of 6: your Daraja credentials (stay in this shell only; nothing is saved to disk)"
read -rsp "Click the COPY icon next to Consumer Key in the portal, then paste here and press Enter (nothing will appear): " KEY; echo
read -rsp "Now the Consumer Secret: copy icon, paste here, press Enter: " SEC; echo
need_len "Consumer Key" "${KEY}"
need_len "Consumer Secret" "${SEC}"
export DARAJA_CONSUMER_KEY="${KEY}" DARAJA_CONSUMER_SECRET="${SEC}" DARAJA_ENVIRONMENT="sandbox" PESA_CONFIG="${BASE}/config.json"
unset KEY SEC

say "Step 5 of 6: OAuth test ('pesa auth')"
if ! "${PESA}" auth; then echo "OAuth failed. Check docs/SANDBOX_SETUP.md, 'If something fails'." >&2; exit 1; fi
echo "OAuth worked."

say "Step 6 of 6: STK Push of KES 1 to Safaricom's public test phone 254708374149"
read -rp "Type YES to continue, or press Enter to stop here: " GO
[[ "${GO}" == "YES" ]] || { echo "Stopped after OAuth."; exit 0; }
PASSKEY="$(curl -fsSL https://raw.githubusercontent.com/gabrielmahia/mpesa-python/main/scripts/sandbox_canary.py | sed -n 's/.*SANDBOX_PASSKEY *= *"\([0-9a-f]\{64\}\)".*/\1/p' | head -1)"
[[ -n "${PASSKEY}" ]] || { echo "Could not read the public sandbox passkey from the repository file." >&2; exit 1; }
export DARAJA_PASSKEY="${PASSKEY}" DARAJA_SHORTCODE="174379"
read -rp "Paste your webhook.site URL (it starts with https://): " CB
[[ "${CB}" == https://* ]] || { echo "The callback URL must start with https://" >&2; exit 1; }
export DARAJA_CALLBACK_URL="${CB}"
"${PESA}" stk push 254708374149 1 --ref TEST
echo; echo "Now look at your webhook.site tab: did a request arrive within about a minute?"
read -rp "Paste the Checkout ID that starts with ws_CO_ to query its status, or press Enter to skip: " ID
if [[ -n "${ID}" ]]; then
  [[ "${ID}" == ws_CO_* ]] || { echo "That is not a Checkout ID. It must start with ws_CO_" >&2; exit 1; }
  "${PESA}" stk query "${ID}"
fi

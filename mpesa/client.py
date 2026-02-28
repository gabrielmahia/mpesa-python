"""MpesaClient — unified entry point for all Daraja v3 operations.

Usage:
    from mpesa import MpesaClient

    client = MpesaClient(
        consumer_key="your_key",
        consumer_secret="your_secret",
        shortcode="174379",           # your paybill or till number
        passkey="your_lnm_passkey",   # from Daraja portal (STK Push only)
        sandbox=True,                 # switch to False for production
    )

    # Prompt customer phone to pay
    result = client.stk_push(
        phone="0712345678",
        amount=500,
        reference="Order-2024-001",
        description="Coffee order",
        callback_url="https://yourapp.com/mpesa/callback",
    )
    print(result.checkout_request_id)  # use to query status

    # Disburse funds to a customer (B2C)
    result = client.b2c(
        phone="0712345678",
        amount=1000,
        remarks="Refund for order 001",
        callback_url="https://yourapp.com/mpesa/b2c/callback",
    )
"""
from __future__ import annotations
import base64
import json
import urllib.request
import urllib.error
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from mpesa.auth import Auth
from mpesa.exceptions import MpesaError, TransactionError, TimeoutError as MpesaTimeoutError
import mpesa.validators as v


@dataclass
class STKResult:
    """Result of a successful STK Push initiation.

    Note: success here means the push was *sent* — not that the user paid.
    Poll with client.stk_query(checkout_request_id) or receive webhook.
    """
    merchant_request_id: str
    checkout_request_id: str
    response_description: str
    customer_message: str
    raw: dict


@dataclass
class B2CResult:
    """Result of a B2C disbursement initiation."""
    conversation_id: str
    originator_conversation_id: str
    response_description: str
    raw: dict


@dataclass
class STKQueryResult:
    """Status of an STK Push transaction."""
    result_code: str  # '0' = success, other codes = failure reasons
    result_desc: str
    merchant_request_id: str
    checkout_request_id: str
    is_paid: bool
    raw: dict


class MpesaClient:
    """Production-grade M-Pesa Daraja v3 client.

    Thread-safe. Token cache is per-instance.
    For async applications, use MpesaAsyncClient (see docs/async.md).
    """

    _SANDBOX_BASE = "https://sandbox.safaricom.co.ke"
    _LIVE_BASE = "https://api.safaricom.co.ke"

    def __init__(
        self,
        consumer_key: str,
        consumer_secret: str,
        shortcode: str | int,
        passkey: str = "",
        sandbox: bool = True,
        timeout: int = 30,
    ):
        """
        Args:
            consumer_key: Daraja app consumer key.
            consumer_secret: Daraja app consumer secret.
            shortcode: Your Paybill or Till number.
            passkey: Lipa Na M-Pesa Online passkey (required for STK Push).
            sandbox: True for test environment, False for production.
            timeout: HTTP request timeout in seconds.
        """
        self._auth = Auth(consumer_key, consumer_secret, sandbox)
        self._shortcode = v.shortcode(shortcode)
        self._passkey = passkey
        self._sandbox = sandbox
        self._timeout = timeout

    @property
    def _base(self) -> str:
        return self._SANDBOX_BASE if self._sandbox else self._LIVE_BASE

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._auth.token()}",
            "Content-Type": "application/json",
        }

    def _post(self, path: str, payload: dict) -> dict:
        url = f"{self._base}{path}"
        body = json.dumps(payload).encode()
        req = urllib.request.Request(url, data=body, headers=self._headers(), method="POST")
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            body_text = e.read()[:400].decode("utf-8", "ignore")
            try:
                err = json.loads(body_text)
                msg = err.get("errorMessage") or err.get("ResultDesc") or body_text[:100]
                code = str(err.get("errorCode") or err.get("ResultCode") or e.code)
            except Exception:
                msg, code = body_text[:100], str(e.code)
            raise MpesaError(f"API error {e.code}: {msg}", code=code, raw={"body": body_text}) from e
        except TimeoutError as e:
            raise MpesaTimeoutError(f"Daraja API timed out after {self._timeout}s") from e
        except OSError as e:
            raise MpesaError(f"Network error: {e}") from e

    def _stk_password(self, timestamp: str) -> str:
        raw = f"{self._shortcode}{self._passkey}{timestamp}"
        return base64.b64encode(raw.encode()).decode()

    # ── STK Push (Lipa Na M-Pesa Online) ─────────────────────────────────────

    def stk_push(
        self,
        phone: str,
        amount: int | float,
        reference: str,
        description: str = "Payment",
        callback_url: str = "",
        transaction_type: str = "CustomerPayBillOnline",
    ) -> STKResult:
        """Initiate an STK Push — prompts the customer's phone to enter their PIN.

        Args:
            phone: Customer phone number (any Kenyan format, normalised automatically).
            amount: Amount in KES (positive integer, max 150,000).
            reference: Your order/reference ID (max 12 chars).
            description: Description shown to customer on their phone.
            callback_url: URL where Safaricom will POST the result (must be HTTPS in production).
            transaction_type: 'CustomerPayBillOnline' (Paybill) or 'CustomerBuyGoodsOnline' (Till).

        Returns:
            STKResult with checkout_request_id. Use this to poll status.

        Raises:
            ValidationError: Parameter validation failed (no network call made).
            AuthenticationError: Could not get OAuth token.
            MpesaError: API returned an error.
        """
        if not self._passkey:
            raise MpesaError("passkey is required for STK Push. Set it in MpesaClient(passkey=...)")

        phone_norm = v.phone(phone)
        amount_norm = v.amount(amount)
        ref_norm = v.account_reference(reference)
        timestamp = v.passkey_timestamp()

        data = self._post("/mpesa/stkpush/v1/processrequest", {
            "BusinessShortCode": self._shortcode,
            "Password": self._stk_password(timestamp),
            "Timestamp": timestamp,
            "TransactionType": transaction_type,
            "Amount": amount_norm,
            "PartyA": phone_norm,
            "PartyB": self._shortcode,
            "PhoneNumber": phone_norm,
            "CallBackURL": callback_url,
            "AccountReference": ref_norm,
            "TransactionDesc": description[:13],  # Daraja limit
        })

        return STKResult(
            merchant_request_id=data.get("MerchantRequestID", ""),
            checkout_request_id=data.get("CheckoutRequestID", ""),
            response_description=data.get("ResponseDescription", ""),
            customer_message=data.get("CustomerMessage", ""),
            raw=data,
        )

    def stk_query(self, checkout_request_id: str) -> STKQueryResult:
        """Query the status of an STK Push transaction.

        Args:
            checkout_request_id: From the STKResult of stk_push().

        Returns:
            STKQueryResult with result_code ('0' = paid) and is_paid bool.
        """
        if not self._passkey:
            raise MpesaError("passkey is required for STK Query.")

        timestamp = v.passkey_timestamp()
        data = self._post("/mpesa/stkpushquery/v1/query", {
            "BusinessShortCode": self._shortcode,
            "Password": self._stk_password(timestamp),
            "Timestamp": timestamp,
            "CheckoutRequestID": checkout_request_id,
        })

        result_code = str(data.get("ResultCode", data.get("errorCode", "-1")))
        return STKQueryResult(
            result_code=result_code,
            result_desc=data.get("ResultDesc", data.get("errorMessage", "")),
            merchant_request_id=data.get("MerchantRequestID", ""),
            checkout_request_id=data.get("CheckoutRequestID", checkout_request_id),
            is_paid=(result_code == "0"),
            raw=data,
        )

    # ── B2C (Business to Customer) ────────────────────────────────────────────

    def b2c(
        self,
        phone: str,
        amount: int | float,
        remarks: str = "Payment",
        occasion: str = "",
        callback_url: str = "",
        queue_timeout_url: str = "",
        initiator_name: str = "",
        security_credential: str = "",
        command_id: str = "BusinessPayment",
    ) -> B2CResult:
        """Disburse funds from your shortcode to a customer's M-Pesa wallet.

        Args:
            phone: Recipient phone number.
            amount: Amount in KES.
            remarks: Transaction description.
            occasion: Optional additional info.
            callback_url: Result notification URL.
            queue_timeout_url: Timeout notification URL.
            initiator_name: API operator username from Daraja portal.
            security_credential: Encrypted initiator password.
            command_id: 'BusinessPayment', 'SalaryPayment', or 'PromotionPayment'.

        Returns:
            B2CResult with conversation_id for status tracking.
        """
        phone_norm = v.phone(phone)
        amount_norm = v.amount(amount)

        data = self._post("/mpesa/b2c/v3/paymentrequest", {
            "OriginatorConversationID": f"b2c-{int(datetime.now().timestamp())}",
            "InitiatorName": initiator_name,
            "SecurityCredential": security_credential,
            "CommandID": command_id,
            "Amount": amount_norm,
            "PartyA": self._shortcode,
            "PartyB": phone_norm,
            "Remarks": remarks[:100],
            "QueueTimeOutURL": queue_timeout_url,
            "ResultURL": callback_url,
            "Occasion": occasion[:100],
        })

        result_code = str(data.get("ResponseCode", "-1"))
        if result_code not in ("0", ""):
            raise TransactionError(
                data.get("ResponseDescription", "B2C request rejected"),
                code=result_code,
                raw=data,
            )

        return B2CResult(
            conversation_id=data.get("ConversationID", ""),
            originator_conversation_id=data.get("OriginatorConversationID", ""),
            response_description=data.get("ResponseDescription", ""),
            raw=data,
        )

    # ── C2B (Customer to Business) ────────────────────────────────────────────

    def c2b_register_urls(
        self,
        validation_url: str,
        confirmation_url: str,
        response_type: str = "Completed",
    ) -> dict:
        """Register C2B callback URLs for your shortcode.

        Call once (or after URL changes). Daraja stores these against your shortcode.

        Args:
            validation_url: Called before transaction — return 'Accepted' or 'Cancelled'.
            confirmation_url: Called after successful payment.
            response_type: 'Completed' (auto-accept) or 'Cancelled' (use validation_url).
        """
        return self._post("/mpesa/c2b/v1/registerurl", {
            "ShortCode": self._shortcode,
            "ResponseType": response_type,
            "ConfirmationURL": confirmation_url,
            "ValidationURL": validation_url,
        })

    # ── Account Balance ───────────────────────────────────────────────────────

    def account_balance(
        self,
        callback_url: str,
        queue_timeout_url: str = "",
        initiator_name: str = "",
        security_credential: str = "",
        identifier_type: str = "4",
    ) -> dict:
        """Query account balance for your shortcode.

        Result delivered asynchronously to callback_url.
        identifier_type: '1'=MSISDN, '2'=Till, '4'=Paybill (default).
        """
        return self._post("/mpesa/accountbalance/v1/query", {
            "Initiator": initiator_name,
            "SecurityCredential": security_credential,
            "CommandID": "AccountBalance",
            "PartyA": self._shortcode,
            "IdentifierType": identifier_type,
            "Remarks": "Balance query",
            "QueueTimeOutURL": queue_timeout_url,
            "ResultURL": callback_url,
        })

    # ── Webhook validation ────────────────────────────────────────────────────

    @staticmethod
    def parse_stk_callback(body: dict) -> dict[str, Any]:
        """Parse an STK Push webhook body into a flat, usable dict.

        Args:
            body: The parsed JSON dict from Safaricom's POST to your callback_url.

        Returns:
            Dict with keys: paid, result_code, result_desc, phone, amount,
                            mpesa_receipt, transaction_date, merchant_request_id,
                            checkout_request_id, raw.
        """
        try:
            cb = body["Body"]["stkCallback"]
            result_code = str(cb.get("ResultCode", "-1"))
            paid = result_code == "0"
            items = {}
            if paid:
                for item in cb.get("CallbackMetadata", {}).get("Item", []):
                    items[item["Name"]] = item.get("Value")
            return {
                "paid": paid,
                "result_code": result_code,
                "result_desc": cb.get("ResultDesc", ""),
                "phone": str(items.get("PhoneNumber", "")),
                "amount": items.get("Amount"),
                "mpesa_receipt": items.get("MpesaReceiptNumber"),
                "transaction_date": items.get("TransactionDate"),
                "merchant_request_id": cb.get("MerchantRequestID"),
                "checkout_request_id": cb.get("CheckoutRequestID"),
                "raw": body,
            }
        except (KeyError, TypeError) as e:
            raise MpesaError(f"Could not parse STK callback: {e}. Raw: {body}") from e

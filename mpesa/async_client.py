"""Optional, native-async Daraja client using aiohttp.

Requires: pip install "daraja-v3[async]". The synchronous SDK remains stdlib-only.
Network requests and OAuth use nonblocking I/O; sync validation/payload helpers
are reused where safe to keep the two clients behaviorally aligned.
"""
from __future__ import annotations

import asyncio
import base64
import json
import time
from datetime import datetime
from typing import TYPE_CHECKING, Any

import mpesa.validators as v
from mpesa.auth import _TokenCache
from mpesa.client import B2CResult, MpesaClient, STKQueryResult, STKResult
from mpesa.exceptions import AuthenticationError, MpesaError, TransactionError
from mpesa.exceptions import TimeoutError as MpesaTimeoutError

if TYPE_CHECKING:
    from aiohttp import ClientSession


class MpesaAsyncClient:
    """Async Daraja v3 transport. Prefer `async with` or call `aclose()`.

    The default synchronous client is unchanged. aiohttp is only required if
    an async client is constructed; it is not imported by ordinary SDK users.
    """

    def __init__(
        self,
        consumer_key: str,
        consumer_secret: str,
        shortcode: str | int,
        passkey: str = "",
        sandbox: bool = True,
        timeout: int = 30,
        base_url: str | None = None,
    ) -> None:
        try:
            import aiohttp
        except ImportError as exc:
            raise ImportError(
                'Native async calls require aiohttp. Install: pip install "daraja-v3[async]"'
            ) from exc
        self._aiohttp = aiohttp
        # Centralize validation, URL policy, and password generation in the
        # existing tested synchronous client. We never call its network methods.
        self._config = MpesaClient(
            consumer_key=consumer_key,
            consumer_secret=consumer_secret,
            shortcode=shortcode,
            passkey=passkey,
            sandbox=sandbox,
            timeout=timeout,
            base_url=base_url,
        )
        self._key = consumer_key
        self._secret = consumer_secret
        self._tokens = _TokenCache()
        self._token_lock = asyncio.Lock()
        self._session: ClientSession | None = None

    def _http(self) -> ClientSession:
        # There is no await before assigning the session; concurrently
        # scheduled tasks on one event loop cannot create duplicate sessions.
        if self._session is None or self._session.closed:
            self._session = self._aiohttp.ClientSession()
        return self._session

    async def __aenter__(self) -> MpesaAsyncClient:
        self._http()
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        """Close idle connections. Call at FastAPI shutdown."""
        if self._session is not None and not self._session.closed:
            await self._session.close()

    async def _token(self) -> str:
        if self._tokens.is_valid():
            return self._tokens.access_token
        async with self._token_lock:
            if self._tokens.is_valid():
                return self._tokens.access_token
            try:
                async with self._http().get(
                    self._config._auth._url,
                    headers={"Authorization": "Basic " + base64.b64encode(
                        f"{self._key}:{self._secret}".encode()
                    ).decode()},
                    timeout=self._aiohttp.ClientTimeout(total=15),
                ) as response:
                    if response.status >= 400:
                        body = (await response.text())[:200]
                        raise AuthenticationError(
                            f"Token request failed ({response.status}): {body}",
                            code=str(response.status),
                        )
                    data = await response.json(content_type=None)
            except asyncio.TimeoutError as exc:
                raise AuthenticationError("Token request timed out") from exc
            except self._aiohttp.ClientError as exc:
                raise AuthenticationError(f"Network error during auth: {exc}") from exc
            except (ValueError, TypeError) as exc:
                raise AuthenticationError("Invalid OAuth response") from exc

            if not isinstance(data, dict) or not data.get("access_token"):
                raise AuthenticationError("No access_token in response", raw=data)
            try:
                lifetime = int(data.get("expires_in", 3600))
            except (ValueError, TypeError) as exc:
                raise AuthenticationError("Invalid expires_in in OAuth response") from exc
            self._tokens.access_token = str(data["access_token"])
            self._tokens.expires_at = time.time() + lifetime
            return self._tokens.access_token

    async def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        token = await self._token()
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        try:
            async with self._http().post(
                f"{self._config._base}{path}",
                json=payload,
                headers=headers,
                timeout=self._aiohttp.ClientTimeout(total=self._config._timeout),
            ) as response:
                response_text = await response.text()
                if response.status >= 400:
                    limited = response_text[:400]
                    try:
                        parsed_error = json.loads(limited)
                        message = parsed_error.get("errorMessage") or parsed_error.get(
                            "ResultDesc"
                        ) or limited[:100]
                        code = str(
                            parsed_error.get("errorCode")
                            or parsed_error.get("ResultCode")
                            or response.status
                        )
                    except (ValueError, AttributeError):
                        message, code = limited[:100], str(response.status)
                    raise MpesaError(
                        f"API error {response.status}: {message}",
                        code=code,
                        raw={"body": limited},
                    )
                try:
                    data = json.loads(response_text)
                except ValueError as exc:
                    raise MpesaError("Invalid JSON response from Daraja") from exc
                if not isinstance(data, dict):
                    raise MpesaError("Expected a JSON object from Daraja")
                return data
        except asyncio.TimeoutError as exc:
            raise MpesaTimeoutError(
                f"Daraja API timed out after {self._config._timeout}s"
            ) from exc
        except self._aiohttp.ClientError as exc:
            raise MpesaError(f"Network error: {exc}") from exc

    async def stk_push(
        self,
        phone: str,
        amount: int | float,
        reference: str,
        description: str = "Payment",
        callback_url: str = "",
        transaction_type: str = "CustomerPayBillOnline",
        party_b: str | int | None = None,
    ) -> STKResult:
        """Initiate a push, NOT confirmation of payment. Supports Buy Goods PartyB."""
        if not self._config._passkey:
            raise MpesaError("passkey is required for STK Push. Set it in MpesaAsyncClient")
        phone_norm = v.phone(phone)
        amount_norm = v.amount(amount)
        reference_norm = v.account_reference(reference)
        timestamp = v.passkey_timestamp()
        party_b_norm = v.shortcode(party_b) if party_b is not None else self._config._shortcode
        data = await self._post("/mpesa/stkpush/v1/processrequest", {
            "BusinessShortCode": self._config._shortcode,
            "Password": self._config._stk_password(timestamp),
            "Timestamp": timestamp,
            "TransactionType": transaction_type,
            "Amount": amount_norm,
            "PartyA": phone_norm,
            "PartyB": party_b_norm,
            "PhoneNumber": phone_norm,
            "CallBackURL": callback_url,
            "AccountReference": reference_norm,
            "TransactionDesc": description[:13],
        })
        return STKResult(
            merchant_request_id=data.get("MerchantRequestID", ""),
            checkout_request_id=data.get("CheckoutRequestID", ""),
            response_description=data.get("ResponseDescription", ""),
            customer_message=data.get("CustomerMessage", ""),
            raw=data,
        )

    async def stk_query(self, checkout_request_id: str) -> STKQueryResult:
        if not self._config._passkey:
            raise MpesaError("passkey is required for STK Query.")
        timestamp = v.passkey_timestamp()
        data = await self._post("/mpesa/stkpushquery/v1/query", {
            "BusinessShortCode": self._config._shortcode,
            "Password": self._config._stk_password(timestamp),
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

    async def b2c(
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
        phone_norm = v.phone(phone)
        amount_norm = v.amount(amount)
        data = await self._post("/mpesa/b2c/v3/paymentrequest", {
            "OriginatorConversationID": f"b2c-{int(datetime.now().timestamp())}",
            "InitiatorName": initiator_name,
            "SecurityCredential": security_credential,
            "CommandID": command_id,
            "Amount": amount_norm,
            "PartyA": self._config._shortcode,
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

    async def c2b_register_urls(
        self,
        validation_url: str,
        confirmation_url: str,
        response_type: str = "Completed",
    ) -> dict[str, Any]:
        return await self._post("/mpesa/c2b/v1/registerurl", {
            "ShortCode": self._config._shortcode,
            "ResponseType": response_type,
            "ConfirmationURL": confirmation_url,
            "ValidationURL": validation_url,
        })

    async def account_balance(
        self,
        callback_url: str,
        queue_timeout_url: str = "",
        initiator_name: str = "",
        security_credential: str = "",
        identifier_type: str = "4",
    ) -> dict[str, Any]:
        return await self._post("/mpesa/accountbalance/v1/query", {
            "Initiator": initiator_name,
            "SecurityCredential": security_credential,
            "CommandID": "AccountBalance",
            "PartyA": self._config._shortcode,
            "IdentifierType": identifier_type,
            "Remarks": "Balance query",
            "QueueTimeOutURL": queue_timeout_url,
            "ResultURL": callback_url,
        })

    @staticmethod
    def parse_stk_callback(body: dict[str, Any]) -> dict[str, Any]:
        """Parse without network I/O; see callback safety notes in docs/async.md."""
        return MpesaClient.parse_stk_callback(body)

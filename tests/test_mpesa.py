"""
mpesa-python test suite — unit tests with no network calls required.
Integration tests (requiring real Daraja sandbox credentials) are in tests/integration/.
"""
import pytest
from mpesa.validators import phone, amount, shortcode, account_reference
from mpesa.exceptions import ValidationError, MpesaError, TransactionError
from mpesa.client import MpesaClient


# ── Phone validation ──────────────────────────────────────────────────────────

class TestPhoneValidator:
    def test_kenyan_07_format(self):
        assert phone("0712345678") == "254712345678"

    def test_kenyan_07_without_leading_zero(self):
        assert phone("712345678") == "254712345678"

    def test_international_format_with_plus(self):
        assert phone("+254712345678") == "254712345678"

    def test_international_format_without_plus(self):
        assert phone("254712345678") == "254712345678"

    def test_strips_spaces(self):
        assert phone("0712 345 678") == "254712345678"

    def test_strips_dashes(self):
        assert phone("0712-345-678") == "254712345678"

    def test_rejects_short_number(self):
        with pytest.raises(ValidationError) as exc_info:
            phone("0712")
        assert "INVALID_PHONE" in str(exc_info.value.code)

    def test_rejects_non_kenyan_number(self):
        with pytest.raises(ValidationError):
            phone("+1 800 555 0100")

    def test_rejects_empty(self):
        with pytest.raises(ValidationError):
            phone("")


# ── Amount validation ─────────────────────────────────────────────────────────

class TestAmountValidator:
    def test_valid_integer(self):
        assert amount(500) == 500

    def test_valid_float_truncates(self):
        assert amount(99.99) == 99  # M-Pesa requires integer KES

    def test_rejects_zero(self):
        with pytest.raises(ValidationError) as exc_info:
            amount(0)
        assert "INVALID_AMOUNT" in str(exc_info.value.code)

    def test_rejects_negative(self):
        with pytest.raises(ValidationError):
            amount(-100)

    def test_rejects_over_limit(self):
        with pytest.raises(ValidationError) as exc_info:
            amount(150_001)
        assert "AMOUNT_EXCEEDS_LIMIT" in str(exc_info.value.code)

    def test_accepts_max_limit(self):
        assert amount(150_000) == 150_000

    def test_rejects_string(self):
        with pytest.raises(ValidationError):
            amount("not_a_number")


# ── Shortcode validation ──────────────────────────────────────────────────────

class TestShortcodeValidator:
    def test_valid_5_digit(self):
        assert shortcode("12345") == "12345"

    def test_valid_6_digit(self):
        assert shortcode("600000") == "600000"

    def test_valid_7_digit(self):
        assert shortcode("1234567") == "1234567"

    def test_accepts_int_input(self):
        assert shortcode(174379) == "174379"

    def test_rejects_4_digit(self):
        with pytest.raises(ValidationError):
            shortcode("1234")

    def test_rejects_alpha(self):
        with pytest.raises(ValidationError):
            shortcode("ABCDE")


# ── Account reference ─────────────────────────────────────────────────────────

class TestAccountReference:
    def test_valid_reference(self):
        assert account_reference("Order-001") == "Order-001"

    def test_truncates_to_12(self):
        result = account_reference("ThisIsAVeryLongReference")
        assert len(result) <= 12

    def test_strips_special_chars(self):
        result = account_reference("Order#001!")
        assert "#" not in result
        assert "!" not in result


# ── Exception structure ───────────────────────────────────────────────────────

class TestExceptions:
    def test_mpesa_error_attributes(self):
        err = MpesaError("Something failed", code="1032", raw={"key": "val"})
        assert err.code == "1032"
        assert err.raw == {"key": "val"}
        assert "1032" in repr(err)

    def test_transaction_error_is_mpesa_error(self):
        err = TransactionError("Insufficient funds", code="1")
        assert isinstance(err, MpesaError)
        assert err.code == "1"

    def test_validation_error_has_no_network_side_effect(self):
        # ValidationError should be raised before any network call
        # We verify this by ensuring it raises even with obviously invalid credentials
        with pytest.raises(ValidationError):
            MpesaClient(
                consumer_key="key",
                consumer_secret="secret",
                shortcode="INVALID",  # ← should fail validation immediately
            )


# ── Client instantiation ──────────────────────────────────────────────────────

class TestClientInstantiation:
    def test_valid_client_creation(self):
        client = MpesaClient(
            consumer_key="test_key",
            consumer_secret="test_secret",
            shortcode="174379",
            passkey="test_passkey",
            sandbox=True,
        )
        assert client._sandbox is True
        assert client._shortcode == "174379"

    def test_stk_push_requires_passkey(self):
        client = MpesaClient("k", "s", "174379")  # no passkey
        with pytest.raises(MpesaError, match="passkey is required"):
            client.stk_push("0712345678", 100, "ref")


# ── Webhook parsing ───────────────────────────────────────────────────────────

class TestWebhookParsing:
    def test_parse_successful_stk_callback(self):
        payload = {
            "Body": {
                "stkCallback": {
                    "MerchantRequestID": "29115-34620561-1",
                    "CheckoutRequestID": "ws_CO_191220201234567890",
                    "ResultCode": 0,
                    "ResultDesc": "The service request is processed successfully.",
                    "CallbackMetadata": {
                        "Item": [
                            {"Name": "Amount", "Value": 1},
                            {"Name": "MpesaReceiptNumber", "Value": "NLJ7RT61SV"},
                            {"Name": "TransactionDate", "Value": 20191219102115},
                            {"Name": "PhoneNumber", "Value": 254708374149},
                        ]
                    },
                }
            }
        }
        result = MpesaClient.parse_stk_callback(payload)
        assert result["paid"] is True
        assert result["mpesa_receipt"] == "NLJ7RT61SV"
        assert result["amount"] == 1
        assert result["result_code"] == "0"

    def test_parse_failed_stk_callback(self):
        payload = {
            "Body": {
                "stkCallback": {
                    "MerchantRequestID": "29115-34620561-1",
                    "CheckoutRequestID": "ws_CO_191220201234567890",
                    "ResultCode": 1032,
                    "ResultDesc": "Request cancelled by user.",
                }
            }
        }
        result = MpesaClient.parse_stk_callback(payload)
        assert result["paid"] is False
        assert result["result_code"] == "1032"

    def test_parse_malformed_callback_raises(self):
        with pytest.raises(MpesaError, match="Could not parse"):
            MpesaClient.parse_stk_callback({"unexpected": "structure"})

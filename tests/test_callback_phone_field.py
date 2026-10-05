"""parse_stk_callback must pass the callback's PhoneNumber through as a string whatever its form (real number, integer, or a masked value)."""
import pytest

from mpesa.client import MpesaClient


def _body(phone):
    return {"Body": {"stkCallback": {"MerchantRequestID": "m1", "CheckoutRequestID": "c1", "ResultCode": 0, "ResultDesc": "ok",
            "CallbackMetadata": {"Item": [{"Name": "Amount", "Value": 100}, {"Name": "MpesaReceiptNumber", "Value": "RCP123"},
                                          {"Name": "TransactionDate", "Value": 20261005120000}, {"Name": "PhoneNumber", "Value": phone}]}}}}


@pytest.mark.parametrize("phone", [254712345678, "254712345678", "0722000***", "254722000***"])
def test_phone_is_returned_as_a_string_and_the_payment_still_parses(phone):
    r = MpesaClient.parse_stk_callback(_body(phone))
    assert r["phone"] == str(phone) and isinstance(r["phone"], str)
    assert r["paid"] is True and r["mpesa_receipt"] == "RCP123" and r["checkout_request_id"] == "c1" and r["amount"] == 100


def test_a_failed_payment_has_an_empty_phone_and_does_not_raise():
    body = {"Body": {"stkCallback": {"MerchantRequestID": "m1", "CheckoutRequestID": "c1", "ResultCode": 1032, "ResultDesc": "Request cancelled by user"}}}
    r = MpesaClient.parse_stk_callback(body)
    assert r["paid"] is False and r["phone"] == ""

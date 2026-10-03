"""
mpesa-python — Production Python SDK for Safaricom M-Pesa Daraja v3.

Quick start:
    from mpesa import MpesaClient
    client = MpesaClient(consumer_key="...", consumer_secret="...", sandbox=True)
    result = client.stk_push(phone="0712345678", amount=100, reference="Order-001")
"""
from mpesa.client import MpesaClient
from mpesa.exceptions import (
    AuthenticationError,
    MpesaError,
    TransactionError,
    ValidationError,
)
from mpesa.exceptions import (
    TimeoutError as MpesaTimeoutError,
)

__version__ = "0.1.1"
__all__ = [
    "MpesaClient",
    "MpesaError",
    "AuthenticationError",
    "ValidationError",
    "TransactionError",
    "MpesaTimeoutError",
]

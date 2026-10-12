"""
mpesa-python — Production Python SDK for Safaricom M-Pesa Daraja v3.

Quick start:
    from mpesa import MpesaClient
    client = MpesaClient(consumer_key="...", consumer_secret="...", sandbox=True)
    result = client.stk_push(phone="0712345678", amount=100, reference="Order-001")
"""
from mpesa.async_client import MpesaAsyncClient
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

try:  # the single source of truth is the installed package's metadata (pyproject.toml)
    from importlib.metadata import version as _pkg_version

    __version__ = _pkg_version("daraja-v3")
except Exception:  # noqa: BLE001  (running from a source tree that is not installed)
    __version__ = "0+unknown"
__all__ = [
    "MpesaClient",
    "MpesaAsyncClient",
    "MpesaError",
    "AuthenticationError",
    "ValidationError",
    "TransactionError",
    "MpesaTimeoutError",
]

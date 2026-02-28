"""M-Pesa SDK exceptions — typed, inspectable, never swallowed."""


class MpesaError(Exception):
    """Base exception for all M-Pesa SDK errors.

    Attributes:
        message: Human-readable error description.
        code: M-Pesa result code where available (e.g., '1032', '2001').
        raw: Raw API response dict for debugging.
    """
    def __init__(self, message: str, code: str | None = None, raw: dict | None = None):
        super().__init__(message)
        self.message = message
        self.code = code
        self.raw = raw or {}

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(code={self.code!r}, message={self.message!r})"


class AuthenticationError(MpesaError):
    """Raised when OAuth token acquisition fails.
    Check CONSUMER_KEY and CONSUMER_SECRET. Tokens expire after 3600 seconds.
    """


class ValidationError(MpesaError):
    """Raised before any API call when request parameters fail local validation.
    No network request was made. Fix the parameter and retry.
    """


class TransactionError(MpesaError):
    """Raised when M-Pesa returns a non-zero ResultCode.

    Common codes:
      1032 — Request cancelled by user
      1037 — DS timeout — user timed out
      2001 — Wrong credentials
      1     — Insufficient funds
    """


class TimeoutError(MpesaError):
    """Raised when the Daraja API does not respond within the configured timeout."""

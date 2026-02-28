"""Input validation before any API call.

All validation raises ValidationError — no network call is made until
parameters pass local validation. This saves quota and gives faster feedback.
"""
from __future__ import annotations
import re
from mpesa.exceptions import ValidationError


_PHONE_RE = re.compile(r"^2547\d{8}$")  # 2547XXXXXXXX — 12 digits


def phone(value: str, field: str = "phone_number") -> str:
    """Normalise and validate a Kenyan phone number to 2547XXXXXXXX format.

    Accepts: 0712345678, +254712345678, 254712345678, 712345678
    Returns: 254712345678
    """
    cleaned = re.sub(r"[\s\-\(\)]", "", str(value))
    if cleaned.startswith("+"):
        cleaned = cleaned[1:]
    if cleaned.startswith("07"):
        cleaned = "254" + cleaned[1:]
    if cleaned.startswith("7"):
        cleaned = "254" + cleaned
    if not _PHONE_RE.match(cleaned):
        raise ValidationError(
            f"Invalid {field}: '{value}'. Expected format: 07XXXXXXXX, +2547XXXXXXXX, or 2547XXXXXXXX",
            code="INVALID_PHONE",
        )
    return cleaned


def amount(value: int | float, field: str = "amount") -> int:
    """Validate and normalise an M-Pesa amount (must be a positive integer in KES)."""
    try:
        amt = int(value)
    except (TypeError, ValueError):
        raise ValidationError(
            f"Invalid {field}: must be a number, got {value!r}",
            code="INVALID_AMOUNT",
        )
    if amt <= 0:
        raise ValidationError(
            f"Invalid {field}: must be > 0, got {amt}",
            code="INVALID_AMOUNT",
        )
    if amt > 150_000:
        raise ValidationError(
            f"Invalid {field}: {amt} exceeds single-transaction limit of KES 150,000",
            code="AMOUNT_EXCEEDS_LIMIT",
        )
    return amt


def shortcode(value: str | int, field: str = "shortcode") -> str:
    """Validate a Safaricom shortcode (5–7 digits)."""
    s = str(value).strip()
    if not re.match(r"^\d{5,7}$", s):
        raise ValidationError(
            f"Invalid {field}: '{value}'. Shortcode must be 5–7 digits.",
            code="INVALID_SHORTCODE",
        )
    return s


def account_reference(value: str) -> str:
    """Validate account reference (max 12 alphanumeric chars, Daraja limit)."""
    ref = re.sub(r"[^a-zA-Z0-9\-]", "", str(value))[:12].strip()
    if not ref:
        raise ValidationError("account_reference cannot be empty", code="INVALID_REFERENCE")
    return ref


def passkey_timestamp() -> str:
    """Generate current timestamp in YYYYMMDDHHmmss format for STK password."""
    from datetime import datetime
    return datetime.now().strftime("%Y%m%d%H%M%S")

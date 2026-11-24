"""M-Pesa Ratiba (standing orders): request building, validation and schedule maths.

Daraja endpoint: POST /standingorder/v1/createStandingOrderExternal.

Ratiba is a *collection*: Safaricom sends the customer a PIN prompt, and the
standing order exists only after the customer approves it on their own phone.
The final outcome arrives at ``callback_url``. Because the customer is debited
repeatedly, every result carries the schedule and the total commitment so the
caller can show it before and after the request.

Ratiba is a commercial Daraja API: live use needs Safaricom's go-live agreement.
"""
from __future__ import annotations

import calendar
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

import mpesa.validators as v
from mpesa.exceptions import ValidationError

PATH = "/standingorder/v1/createStandingOrderExternal"

# name -> (Safaricom code, step); step None means Safaricom does not define the interval precisely.
FREQUENCIES: dict[str, tuple[str, tuple[str, int] | None]] = {
    "one_off": ("1", None),
    "daily": ("2", ("days", 1)),
    "weekly": ("3", ("days", 7)),
    "monthly": ("4", ("months", 1)),
    "bi_monthly": ("5", None),
    "quarterly": ("6", ("months", 3)),
    "half_year": ("7", ("months", 6)),
    "yearly": ("8", ("months", 12)),
}
_CODE_TO_NAME = {code: name for name, (code, _) in FREQUENCIES.items()}

# receiver -> (TransactionType, ReceiverPartyIdentifierType). "Marchant" is Safaricom's own spelling.
RECEIVERS = {
    "paybill": ("Standing Order Customer Pay Bill", "4"),
    "till": ("Standing Order Customer Pay Marchant", "2"),
}


@dataclass
class RatibaSchedule:
    """What the customer is agreeing to. ``payments``/``total_commitment_kes`` are None when Safaricom's
    frequency is ambiguous (bi_monthly); Safaricom's own schedule is authoritative in every case."""
    frequency: str
    amount_kes_each: int
    start_date: date
    end_date: date
    payments: int | None
    total_commitment_kes: int | None


@dataclass
class RatibaResult:
    """Result of a Ratiba request. ``accepted`` means Safaricom ACCEPTED the request and sent the PIN prompt;
    the standing order exists only after the customer approves, which is reported to ``callback_url``."""
    accepted: bool
    response_ref_id: str
    response_code: str
    response_description: str
    schedule: RatibaSchedule
    raw: dict[str, Any]


def frequency(value: str | int) -> str:
    """Normalise a frequency name (``monthly``, ``half-year``...) or Safaricom code (1-8) to its name."""
    f = str(value).strip().lower().replace("-", "_").replace(" ", "_")
    f = _CODE_TO_NAME.get(f, f)
    if f not in FREQUENCIES:
        raise ValidationError(f"Invalid frequency {value!r}: use one of {sorted(FREQUENCIES)} or codes 1-8",
                              code="INVALID_FREQUENCY")
    return f


def parse_date(value: str | date, field: str) -> date:
    """Accept a date, ``YYYY-MM-DD`` or ``YYYYMMDD``."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip().replace("-", "")
    if not re.fullmatch(r"\d{8}", text):
        raise ValidationError(f"Invalid {field}: {value!r} must be YYYY-MM-DD or YYYYMMDD", code="INVALID_DATE")
    try:
        return datetime.strptime(text, "%Y%m%d").date()
    except ValueError as e:
        raise ValidationError(f"Invalid {field}: {value!r} is not a real date", code="INVALID_DATE") from e


def _add_months(d: date, n: int) -> date:
    y, m = divmod(d.month - 1 + n, 12)
    year, month = d.year + y, m + 1
    return d.replace(year=year, month=month, day=min(d.day, calendar.monthrange(year, month)[1]))


def count_payments(start: date, end: date, freq: str) -> int | None:
    """Number of debits from start to end inclusive, or None where Safaricom's interval is undefined."""
    if freq == "one_off":
        return 1
    step = FREQUENCIES[freq][1]
    if step is None:
        return None
    count, k, d = 0, 0, start
    while d <= end and count < 100_000:
        count += 1
        k += 1
        d = start + timedelta(days=step[1] * k) if step[0] == "days" else _add_months(start, step[1] * k)
    return count


def build(
    *,
    shortcode: str,
    phone: str,
    amount: int | float,
    standing_order_name: str,
    start_date: str | date,
    end_date: str | date,
    account_reference: str,
    callback_url: str,
    frequency_: str | int = "monthly",
    receiver_type: str = "paybill",
    description: str = "Standing order",
    today: date | None = None,
) -> tuple[dict[str, Any], RatibaSchedule]:
    """Validate everything locally and return (Daraja payload, schedule). No network call."""
    freq = frequency(frequency_)
    recv = str(receiver_type).strip().lower()
    if recv not in RECEIVERS:
        raise ValidationError("Invalid receiver_type: use 'paybill' or 'till'", code="INVALID_RECEIVER")
    phone_norm = v.phone(phone)
    amount_norm = v.amount(amount)
    name = str(standing_order_name or "").strip()
    if not 1 <= len(name) <= 60:
        raise ValidationError("standing_order_name must be 1 to 60 characters (unique per customer)",
                              code="INVALID_NAME")
    ref = v.account_reference(account_reference)
    if not str(callback_url).startswith("https://"):
        raise ValidationError("callback_url must be an https:// URL; the outcome is only reported there",
                              code="INVALID_CALLBACK")
    start, end = parse_date(start_date, "start_date"), parse_date(end_date, "end_date")
    if start < (today or date.today()):
        raise ValidationError("start_date is in the past", code="INVALID_DATE")
    if end < start:
        raise ValidationError("end_date is before start_date", code="INVALID_DATE")

    payments = count_payments(start, end, freq)
    schedule = RatibaSchedule(
        frequency=freq, amount_kes_each=amount_norm, start_date=start, end_date=end, payments=payments,
        total_commitment_kes=amount_norm * payments if payments is not None else None,
    )
    tx_type, receiver_code = RECEIVERS[recv]
    payload = {
        "StandingOrderName": name,
        "StartDate": start.strftime("%Y%m%d"),
        "EndDate": end.strftime("%Y%m%d"),
        "BusinessShortCode": shortcode,
        "TransactionType": tx_type,
        "ReceiverPartyIdentifierType": receiver_code,
        "Amount": str(amount_norm),
        "PartyA": phone_norm,
        "CallBackURL": callback_url,
        "AccountReference": ref,
        "TransactionDesc": str(description or "")[:13],
        "Frequency": FREQUENCIES[freq][0],
    }
    return payload, schedule


def parse_response(data: dict[str, Any], schedule: RatibaSchedule) -> RatibaResult:
    header = data.get("ResponseHeader") or data.get("responseHeader") or {}
    code = str(header.get("responseCode", data.get("ResponseCode", "")))
    return RatibaResult(
        accepted=code in ("200", "0"),
        response_ref_id=str(header.get("responseRefID", "")),
        response_code=code,
        response_description=str(header.get("responseDescription") or header.get("ResultDesc")
                                 or data.get("ResponseDescription", "")),
        schedule=schedule,
        raw=data,
    )

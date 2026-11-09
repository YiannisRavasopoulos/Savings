"""Money is integer cents. Parsing user input and formatting as €1,234.56."""
from __future__ import annotations

import re
from decimal import Decimal

MAX_CENTS = 100_000_000  # €1,000,000.00 — anything larger is surely a typo
_NUMBER = re.compile(r"(\d+)?(\.\d{1,2})?")


def parse_amount(text: str) -> int:
    """Parse '12', '12.5', '12,50', '€1,234.56' or '1.234,56' into cents.

    Raises ValueError with a message suitable for showing to the user.
    """
    s = (text or "").strip().replace("€", "").replace(" ", "").replace(" ", "")
    if not s:
        raise ValueError("Enter an amount.")
    if s.startswith("-"):
        raise ValueError("Amount can't be negative.")
    if "," in s and "." in s:
        # Both present: the last one is the decimal separator, the other groups thousands.
        cut = max(s.rfind(","), s.rfind("."))
        s = s[:cut].replace(",", "").replace(".", "") + "." + s[cut + 1:]
    else:
        s = s.replace(",", ".")
    m = _NUMBER.fullmatch(s)
    if not m or not (m.group(1) or m.group(2)):
        raise ValueError("Enter a number like 12.50 (at most 2 decimals).")
    cents = int(Decimal(s) * 100)
    if cents > MAX_CENTS:
        raise ValueError("That amount is too large.")
    return cents


def format_eur(cents: int | None) -> str:
    if cents is None:
        return ""
    sign = "-" if cents < 0 else ""
    cents = abs(int(cents))
    return f"{sign}€{cents // 100:,}.{cents % 100:02d}"


def cents_to_input(cents: int | None) -> str:
    """Value to prefill an amount input with, e.g. 1250 -> '12.50'."""
    if cents is None:
        return ""
    return f"{cents // 100}.{cents % 100:02d}"

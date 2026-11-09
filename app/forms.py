"""Validation of submitted forms. Returns (clean values, errors, raw values)."""
from __future__ import annotations

from datetime import date

from .money import cents_to_input, parse_amount

MAX_TEXT = 200
MAX_NOTES = 1000


def parse_date(text: str) -> date:
    d = date.fromisoformat((text or "").strip())
    if not 2000 <= d.year <= 2100:
        raise ValueError
    return d


def _raw(form, fields) -> dict:
    return {f: (form.get(f) or "").strip() for f in fields}


def _date(raw, clean, errors):
    try:
        clean["date"] = parse_date(raw["date"]).isoformat()
    except ValueError:
        errors["date"] = "Enter a valid date."


def _text(raw, clean, errors, field, required, limit):
    value = raw[field]
    if required and not value:
        errors[field] = "Required."
    elif len(value) > limit:
        errors[field] = f"Keep it under {limit} characters."
    clean[field] = value


def _amount(raw, clean, errors):
    try:
        clean["amount_cents"] = parse_amount(raw["amount"])
        if clean["amount_cents"] <= 0:
            errors["amount"] = "Amount must be more than zero."
    except ValueError as e:
        errors["amount"] = str(e)


EXPENSE_FIELDS = ("date", "description", "category_id", "amount", "notes", "one_off")
INCOME_FIELDS = ("date", "description", "amount", "notes")


def validate_expense(form, allowed_category_ids: set[int]):
    raw = _raw(form, EXPENSE_FIELDS)
    clean, errors = {}, {}
    _date(raw, clean, errors)
    _text(raw, clean, errors, "description", True, MAX_TEXT)
    try:
        cid = int(raw["category_id"])
        if cid not in allowed_category_ids:
            raise ValueError
        clean["category_id"] = cid
    except ValueError:
        errors["category_id"] = "Pick a category."
    _amount(raw, clean, errors)
    _text(raw, clean, errors, "notes", False, MAX_NOTES)
    clean["one_off"] = 1 if raw["one_off"] in ("1", "on", "true") else 0
    return clean, errors, raw


def validate_income(form):
    raw = _raw(form, INCOME_FIELDS)
    clean, errors = {}, {}
    _date(raw, clean, errors)
    _text(raw, clean, errors, "description", True, MAX_TEXT)
    _amount(raw, clean, errors)
    _text(raw, clean, errors, "notes", False, MAX_NOTES)
    return clean, errors, raw


def empty_expense(day: str) -> dict:
    return {"date": day, "description": "", "category_id": "", "amount": "", "notes": "", "one_off": ""}


def empty_income(day: str) -> dict:
    return {"date": day, "description": "", "amount": "", "notes": ""}


def expense_values(row) -> dict:
    return {
        "date": row["date"],
        "description": row["description"],
        "category_id": str(row["category_id"]),
        "amount": cents_to_input(row["amount_cents"]),
        "notes": row["notes"],
        "one_off": "1" if row["one_off"] else "",
    }


def income_values(row) -> dict:
    return {
        "date": row["date"],
        "description": row["description"],
        "amount": cents_to_input(row["amount_cents"]),
        "notes": row["notes"],
    }

"""CSV import of expenses: parse and check every row (preview), then save the good ones.

Stateless: the preview page carries the file's text in a hidden field and the confirm step
parses it again, so nothing half-imported is ever stored.

Accepted columns (header row required, names are case-insensitive, extra columns are ignored):
  date (required)       2026-11-05, 05/11/2026, 05.11.2026 or 05-11-2026 (day first)
  amount (required)     12.50, 12,50, €1.234,56 ... or amount_cents (this app's own export)
  description, category, notes, one_off (optional)
Bank exports: when the file has negative amounts, those are the spending (made positive) and
positive amounts (money in) are skipped. A paid_by_me column (this app's export) skips rows
someone else paid.
"""
from __future__ import annotations

import csv
import io
import re
from datetime import date

from . import db, forms, joint
from .money import parse_amount

MAX_BYTES = 2 * 1024 * 1024
MAX_ROWS = 5000
MAX_CATEGORY_NAME = 50
NO_DESCRIPTION = "Imported expense"

ALIASES = {
    "date": ("date", "day", "transaction_date", "booking_date", "value_date", "posted", "when"),
    "description": ("description", "desc", "name", "item", "details", "payee", "merchant", "title", "text"),
    "category": ("category", "cat", "type"),
    "amount": ("amount", "amount_eur", "amount_€", "value", "cost", "price", "sum", "total"),
    "amount_cents": ("amount_cents",),
    "notes": ("notes", "note", "memo", "comment", "comments"),
    "one_off": ("one_off", "oneoff", "one-off"),
    "paid_by_me": ("paid_by_me",),
}
_DMY = re.compile(r"(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{4})")


class ImportError_(ValueError):
    """The file as a whole can't be read (shown at the top of the page)."""


def decode(data: bytes) -> str:
    if len(data) > MAX_BYTES:
        raise ImportError_(f"The file is larger than {MAX_BYTES // (1024 * 1024)} MB.")
    for enc in ("utf-8-sig", "cp1252"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    raise ImportError_("Couldn't read the file's text. Save it as CSV (UTF-8) and try again.")


def _key(header: str) -> str:
    h = header.strip().lower().replace("(€)", "").replace("(eur)", "").strip()
    return re.sub(r"\s+", "_", h)


def _columns(headers: list[str]) -> dict[str, int]:
    keys = [_key(h) for h in headers]
    found = {}
    for field, names in ALIASES.items():
        for i, k in enumerate(keys):
            if k in names and field not in found:
                found[field] = i
    if "date" not in found:
        raise ImportError_("No “date” column found. The first row must name the columns, e.g. "
                           "date, description, category, amount.")
    if "amount" not in found and "amount_cents" not in found:
        raise ImportError_("No “amount” column found.")
    return found


def parse_day(text: str) -> date:
    t = (text or "").strip()
    m = _DMY.fullmatch(t)
    if m:
        d = date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        if not 2000 <= d.year <= 2100:
            raise ValueError
        return d
    return forms.parse_date(t[:10])


def _signed_amount(text: str) -> int:
    """Cents, keeping the sign (bank exports mark spending as negative)."""
    t = (text or "").strip().replace("−", "-")
    neg = t.startswith("-") or (t.startswith("(") and t.endswith(")"))
    t = t.lstrip("-").strip("()")
    if t.endswith("-"):              # "12,50-"
        neg, t = True, t[:-1]
    cents = parse_amount(t)
    return -cents if neg else cents


def parse(conn, uid: int, text: str, *, default_category_id: int | None, create_missing: bool) -> dict:
    """Every row checked, nothing saved. Rows: {line, date, description, category, category_id,
    new_category, amount_cents, notes, one_off, status, reason}; status is ok, duplicate, skip
    or error."""
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    reader = csv.reader(io.StringIO(text), dialect)
    try:
        headers = next(reader)
    except StopIteration:
        raise ImportError_("The file is empty.") from None
    cols = _columns(headers)
    raw_rows = []
    for line, row in enumerate(reader, start=2):
        if not any(cell.strip() for cell in row):
            continue
        raw_rows.append((line, row))
        if len(raw_rows) > MAX_ROWS:
            raise ImportError_(f"The file has more than {MAX_ROWS} rows. Split it and import the parts.")
    if not raw_rows:
        raise ImportError_("The file has a header row but no expenses.")

    def cell(row, field):
        i = cols.get(field)
        return row[i].strip() if i is not None and i < len(row) else ""

    cats = db.active_categories(conn, uid)
    by_name: dict[str, dict] = {}
    for c in cats:                                     # own categories win over shared ones of the same name
        by_name.setdefault(c["name"].casefold(), dict(c))
    default = next((dict(c) for c in cats if c["id"] == default_category_id), None)

    # bank style: any negative amount means negatives are spending, positives money in
    signed = []
    for line, row in raw_rows:
        try:
            signed.append(int(cell(row, "amount_cents")) if "amount_cents" in cols and cell(row, "amount_cents")
                          else _signed_amount(cell(row, "amount")))
        except ValueError as e:
            signed.append(e)
    bank_style = any(isinstance(v, int) and v < 0 for v in signed)

    existing = {(r[0], r[1], r[2].casefold()) for r in conn.execute(
        "SELECT date, amount_cents, description FROM expenses WHERE user_id = ?", (uid,))}
    rows, new_names = [], {}
    for (line, row), amount in zip(raw_rows, signed):
        r = {"line": line, "date": "", "description": cell(row, "description") or NO_DESCRIPTION,
             "category": cell(row, "category"), "category_id": None, "new_category": False,
             "amount_cents": None, "notes": cell(row, "notes")[:forms.MAX_NOTES],
             "one_off": 1 if cell(row, "one_off").lower() in ("1", "yes", "true", "y", "x") else 0,
             "status": "ok", "reason": ""}
        rows.append(r)

        def bad(reason, status="error"):
            r["status"], r["reason"] = status, reason

        if cell(row, "paid_by_me") in ("0", "false"):
            bad("Paid by someone else (shared category).", "skip")
            continue
        try:
            r["date"] = parse_day(cell(row, "date")).isoformat()
        except (ValueError, TypeError):
            bad(f"Date “{cell(row, 'date')}” isn't a date (use 2026-11-05 or 05/11/2026).")
            continue
        if isinstance(amount, ValueError):
            bad(f"Amount: {amount}")
            continue
        if bank_style and amount > 0:
            bad("Money in (positive amount), not spending.", "skip")
            continue
        r["amount_cents"] = abs(amount)
        if r["amount_cents"] == 0:
            bad("Amount is zero.", "skip")
            continue
        if len(r["description"]) > forms.MAX_TEXT:
            r["description"] = r["description"][:forms.MAX_TEXT]

        name = " ".join(r["category"].split())
        if not name:
            if default is None:
                bad("No category. Pick one for rows without a category below.")
                continue
            cat = default
        else:
            cat = by_name.get(name.casefold())
            if cat is None:
                if not create_missing:
                    bad(f"No category called “{name}”. Tick “Create missing categories” or rename it in the file.")
                    continue
                if len(name) > MAX_CATEGORY_NAME:
                    bad(f"Category name is longer than {MAX_CATEGORY_NAME} characters.")
                    continue
                if conn.execute("SELECT 1 FROM categories WHERE user_id = ? AND name = ? COLLATE NOCASE",
                                (uid, name)).fetchone():
                    bad(f"“{name}” is one of your archived categories. Unarchive it first, or use another name.")
                    continue
                key = name.casefold()
                new_names.setdefault(key, name)
                r["category"], r["new_category"] = new_names[key], True
                r["category_id"] = None
        if not r["new_category"]:
            r["category"], r["category_id"] = cat["name"], cat["id"]
            if cat["is_joint"]:
                reason = joint.can_log_on(conn, cat["id"], uid, date.fromisoformat(r["date"]))
                if reason:
                    bad(reason)
                    continue
        if (r["date"], r["amount_cents"], r["description"].casefold()) in existing:
            bad("Looks like it's already in the app (same date, amount and description).", "duplicate")

    counts = {k: sum(1 for r in rows if r["status"] == k) for k in ("ok", "duplicate", "skip", "error")}
    return {"rows": rows, "counts": counts, "new_categories": sorted(new_names.values(), key=str.casefold),
            "bank_style": bank_style, "columns": sorted(cols)}
